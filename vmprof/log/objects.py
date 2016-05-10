import sys
import struct
import argparse
from collections import defaultdict
from vmprof.log import constants as const, merge_point

PY3 = sys.version_info[0] >= 3

class FlatOp(object):
    def __init__(self, opnum, opname, args, result, descr=None, descr_number=None):
        self.opnum = opnum
        self.opname = opname
        self.args = args
        self.result = result
        self.descr = descr
        self.descr_number = descr_number
        self.core_dump = None

    def has_descr(self, descr=None):
        if not descr:
            return self.descr is not None
        return descr == self.descr_number

    def set_core_dump(self, rel_pos, core_dump):
        self.core_dump = (rel_pos, core_dump)

    def get_core_dump(self, base_addr, patches, timeval):
        coredump = self.core_dump[1][:]
        for timepos, addr, content in patches:
            if timeval < timepos:
                continue # do not apply the patch
            op_off = self.core_dump[0]
            patch_start = (addr - base_addr) - op_off 
            patch_end = patch_start + len(content)
            content_end = len(content)-1
            if patch_end >= len(coredump):
                patch_end = len(coredump)
                content_end = patch_end - patch_start
            coredump = coredump[:patch_start] + content[:content_end] + coredump[patch_end:]
        return coredump

    def __repr__(self):
        suffix = ''
        if self.result is not None:
            suffix = "%s = " % self.result
        descr = self.descr
        if descr is None:
            descr = ''
        else:
            descr = ', @' + descr
        return '%s%s(%s%s)' % (suffix, self.opname,
                                ', '.join(self.args), descr)

    def pretty_print(self):
        suffix = ''
        if self.result is not None and self.result != '?':
            suffix = "%s = " % self.result
        descr = self.descr
        if descr is None:
            descr = ''
        else:
            descr = ', @' + descr
        return '%s%s(%s%s)' % (suffix, self.opname,
                                ', '.join(self.args), descr)

    def _serialize(self):
        dict = { 'num': self.opnum,
                 'args': self.args }
        if self.result:
            dict['res'] = self.result
        if self.descr:
            dict['descr'] = self.descr
        if self.core_dump:
             dict['dump'] = self.core_dump
        if self.descr_number:
             dict['descr_number'] = hex(self.descr_number)
        return dict

class MergePoint(FlatOp):
    def __init__(self, values):
        self.values = values

    def get_source_line(self):
        filename = None
        lineno = None
        for sem_type, value in self.values:
            name = const.SEM_TYPE_NAMES[sem_type]
            if name == "filename":
                filename = value
            if name == "lineno":
                lineno = value
        if filename is None or lineno is None:
            return 0, None
        return lineno, filename

    def has_descr(self, descr=None):
        return False

    def set_core_dump(self, rel_pos, core_dump):
        raise NotImplementedError

    def get_core_dump(self, base_addr, patches, timeval):
        raise NotImplementedError

    def __repr__(self):
        return 'debug_merge_point(xxx)'

    def pretty_print(self):
        return 'impl me debug merge point'

    def _serialize(self):
        dict = {}
        for sem_type, value in self.values:
            name = const.SEM_TYPE_NAMES[sem_type]
            dict[name] = value
        return dict

class Stage(object):
    def __init__(self, mark, timeval):
        self.mark = mark
        self.ops = []
        self.timeval = timeval

    def get_last_op(self):
        if len(self.ops) == 0:
            return None
        return self.ops[-1]

    def get_ops(self):
        return self.ops

    def _serialize(self):
        ops = []
        merge_points = defaultdict(list)
        # merge points is a dict mapping from index -> merge_points
        dict = { 'ops': ops, 'tick': self.timeval, 'merge_points': merge_points }
        for op in self.ops:
            result = op._serialize()
            if isinstance(op, MergePoint):
                index = len(ops)
                merge_points[index].append(result)
                if len(merge_points) == 1:
                    # fast access for the first debug merge point!
                    merge_points['first'] = index
            else:
                ops.append(result)
        return dict

class Trace(object):
    def __init__(self, forest, trace_type, tick, unique_id):
        self.forest = forest
        self.type = trace_type
        self.inputargs = []
        assert self.type in ('loop', 'bridge')
        self.unique_id = unique_id
        self.stages = {}
        self.last_mark = None
        self.addrs = (-1,-1)
        # this saves a quadrupel for each
        self.my_patches = None
        self.bridges = []
        self.descr_numbers = set()
        self.counter = 0
        self.merge_point_files = defaultdict(list)

    def pretty_print(self, args):
        stage = self.stages.get(args.stage, None)
        if not stage:
            return ""
        resop = []

        for op in stage.ops:
            resop.append(op.pretty_print())

        return '\n'.join(resop)

    def get_stage(self, type):
        assert type is not None
        return self.stages[type]

    def stitch_bridge(self, timeval, descr_number, addr_to):
        self.bridges.append((timeval, descr_number, addr_to))

    def start_mark(self, mark):
        mark_name = 'noopt'
        if mark == const.MARK_TRACE_OPT:
            mark_name = 'opt'
        elif mark == const.MARK_TRACE_ASM:
            mark_name = 'asm'
        else:
            assert mark == const.MARK_TRACE
            if self.last_mark == mark_name:
                # NOTE unrolling
                #
                # this case means that the optimizer has been invoked
                # twice (see compile_loop in rpython/jit/metainterp/compile.py)
                # and the loop was unrolled in between.
                #
                # we just return here, which means the following ops will just append the loop
                # ops to the preamble ops to the current stage!
                return
        self.last_mark = mark_name
        assert mark_name is not None
        tick = self.forest.timepos
        self.stages[mark_name] = Stage(mark_name, tick)

    def get_last_stage(self):
        return self.stages.get(self.last_mark, None)

    def set_core_dump_to_last_op(self, rel_pos, dump):
        assert self.last_mark is not None
        flatop = self.get_stage(self.last_mark).get_last_op()
        flatop.set_core_dump(rel_pos, dump)

    def add_instr(self, op):
        if op.has_descr():
            self.descr_numbers.add(op.descr_number)
        ops = self.get_stage(self.last_mark).get_ops()
        ops.append(op)

        if isinstance(op, MergePoint):
            lineno, filename = op.get_source_line()
            if filename:
                self.merge_point_files[filename].append(lineno)

    def is_bridge(self):
        return self.type == 'bridge'

    def set_inputargs(self, args):
        self.inputargs = args

    def set_addr_bounds(self, a, b):
        self.addrs = (a,b)

    def contains_addr(self, addr):
        return self.addrs[0] <= addr <= self.addrs[1]

    def contains_patch(self, addr):
        if self.addrs is None:
            return False
        return self.addrs[0] <= addr <= self.addrs[1]

    def get_core_dump(self, timeval=-1, opslice=(0,-1)):
        if timeval == -1:
            timeval = 2**31-1 # a very high number
        if self.my_patches is None:
            self.my_patches = []
            for patch in self.forest.patches:
                patch_time, addr, content = patch
                if self.contains_patch(addr):
                    self.my_patches.append(patch)

        core_dump = []
        start,end = opslice
        if end == -1:
            end = len(opslice)
        ops = None
        stage = self.get_stage('asm')
        if not stage:
            return None # no core dump!
        for i, op in enumerate(stage.get_ops()[start:end]):
            dump = op.get_core_dump(self.addrs[0], self.my_patches, timeval)
            core_dump.append(dump)
        return ''.join(core_dump)

    def _serialize(self):
        bridges = []
        for bridge in self.bridges:
            bridges.append({ 'time': bridge[0],
                             'descr_number': hex(bridge[1]),
                             'target': hex(bridge[2]),
                           })
        stages = {}
        dict = { 'unique_id': hex(self.unique_id),
                 'type': self.type,
                 'args': self.inputargs,
                 'stages': stages,
                 'bridges': bridges,
                 'counter': self.counter,
               }

        for markname, stage in self.stages.items():
            stages[markname] = stage._serialize()
        if self.addrs != (-1,-1):
            dict['addr'] = (hex(self.addrs[0]), hex(self.addrs[1]))
        return dict

def iter_ranges(numbers):
    if len(numbers) == 0:
        raise StopIteration
    numbers.sort()
    first = numbers[0]
    last = numbers[0]
    for pos, i in enumerate(numbers[1:]):
        if (i - first) > 50:
            yield range(first, last+1)
            if pos+1 < len(numbers):
                last = i
                first = i
            else:
                raise StopIteration
        else:
            last = i
    yield range(first, last+1)

class TraceForest(object):
    def __init__(self, version, keep_data=True):
        self.version = version
        self.roots = []
        self.traces = {}
        self.addrs = {}
        self.last_trace = None
        self.resops = {}
        self.timepos = 0
        self.patches = []
        self.keep = keep_data
        # a mapping from source file name -> [(lineno, line)]
        self.source_lines = defaultdict(list)

    def extract_source_code_lines(self):
        file_contents = {}
        for _, trace in self.traces.items():
            for file, lines in trace.merge_point_files.items():
                if file not in file_contents:
                    with open(file, 'rb') as fd:
                        data = fd.read()
                        if PY3:
                            data = data.encode('utf-8')
                        file_contents[file] = data.splitlines()
                split_lines = file_contents[file]
                saved_lines = self.source_lines[file]
                for range in iter_ranges(lines):
                    for r in range:
                        saved_lines.append((r, split_lines[r-1]))

    def get_trace(self, id):
        return self.traces.get(id, None)

    def get_trace_by_addr(self, addr):
        return self.addrs.get(addr, None)

    def add_trace(self, trace_type, unique_id):
        trace = Trace(self, trace_type, self.timepos, unique_id)
        self.traces[unique_id] = trace
        self.last_trace = trace
        return trace

    def stitch_bridge(self, descr_number, addr_to):
        for tid, trace in self.traces.items():
            if descr_number in trace.descr_numbers:
                trace.stitch_bridge(self.timepos, descr_number, addr_to)
                break
        else:
            raise NotImplementedError

    def patch_memory(self, addr, content, timeval):
        self.patches.append((timeval, addr, content))

    def time_tick(self):
        self.timepos += 1

    def is_jitlog_marker(self, marker):
        if marker == '':
            return False
        assert len(marker) == 1
        return const.MARK_JITLOG_START <= marker <= const.MARK_JITLOG_END

    def encode_source_code_lines(self):
        marks = []
        for filename, lines in self.source_lines.items():
            marks.append(const.MARK_SOURCE_CODE)
            data = filename
            if PY3:
                data = data.decode('utf-8')
            marks.append(struct.pack('>I', len(data)))
            marks.append(data)

            marks.append(struct.pack('>I', len(lines)))
            for lineno, line in lines:
                data = line.lstrip()
                diff = len(line) - len(data)
                indent = diff
                for i in range(0, diff):
                    if line[i] == '\t':
                        indent += 7
                if PY3:
                    data = data.decode('utf-8')
                marks.append(struct.pack('>HBI', lineno, indent, len(data)))
                marks.append(data)
        return ''.join(marks)

    def _serialize(self):
        traces = [trace._serialize() for trace in self.traces.values()]
        return { 'resops': self.resops, 'traces': traces }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("jitlog")
    parser.add_argument("--stage", default='asm', help='Which stage should be outputted to stdout')
    args = parser.parse_args()

    trace_forest = read_jitlog(args.jitlog)
    print(trace_forest)
    stage = args.stage
    for _, trace in trace_forest.traces.items():
        text = trace.pretty_print(args)
        print(text)

if __name__ == '__main__':
    main()