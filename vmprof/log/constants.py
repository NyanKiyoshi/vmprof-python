# generated constants from rpython/rlib/jitlog.py
MARK_JITLOG_START = chr(0x10)
MARK_INPUT_ARGS = chr(0x11)
MARK_RESOP_META = chr(0x12)
MARK_RESOP = chr(0x13)
MARK_RESOP_DESCR = chr(0x14)
MARK_ASM_ADDR = chr(0x15)
MARK_ASM = chr(0x16)
MARK_TRACE = chr(0x17)
MARK_TRACE_OPT = chr(0x18)
MARK_TRACE_ASM = chr(0x19)
MARK_STITCH_BRIDGE = chr(0x1a)
MARK_START_TRACE = chr(0x1b)
MARK_JITLOG_COUNTER = chr(0x1c)
MARK_INIT_MERGE_POINT = chr(0x1d)
MARK_JITLOG_HEADER = chr(0x1e)
MARK_MERGE_POINT = chr(0x1f)
MARK_COMMON_PREFIX = chr(0x20)
MARK_ABORT_TRACE = chr(0x21)
MARK_JITLOG_END = chr(0x22)
MP_STR = (0x0,"s")
MP_INT = (0x0,"i")
MP_FILENAME = (0x1,"s")
MP_LINENO = (0x2,"i")
MP_INDEX = (0x4,"i")
MP_SCOPE = (0x8,"s")
MP_OPCODE = (0x10,"s")
SEM_TYPE_NAMES = {
    0x10: "opcode",
    0x8: "scope",
    0x1: "filename",
    0x4: "index",
    0x2: "lineno",
}
