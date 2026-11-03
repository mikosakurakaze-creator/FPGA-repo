import ctypes as C
class Status(C.LittleEndianStructure):
    _fields_=[('abi',C.c_uint32),('attempted',C.c_uint32),('pending',C.c_uint32),('completed',C.c_uint32),
              ('error',C.c_int32),('ctrl',C.c_uint32),('core_return',C.c_uint32),('completed_nodes',C.c_uint32),
              ('hardware_model',C.c_uint32),('hardware_abi',C.c_uint32),('guards_ok',C.c_uint32),('reserved',C.c_uint32),
              ('elapsed_ns',C.c_uint64),('clock_hz',C.c_uint64),('dma',C.c_uint64*84)]
assert C.sizeof(Status)==736
