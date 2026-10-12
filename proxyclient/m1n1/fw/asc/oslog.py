# SPDX-License-Identifier: MIT
from .base import *
from ...utils import *

## OSLog endpoint

class OSLogMessage(Register64):
    TYPE = 63, 56

class OSLog_GetBuf(OSLogMessage):
    TYPE = 63, 56, Constant(1)
    SIZE = 55, 36
    DVA = 35, 0

class ASCOSLogEndpoint(ASCBaseEndpoint):
    BASE_MESSAGE = OSLogMessage
    SHORT = "oslog"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.iobuffer = None
        self.iobuffer_dva = None

    @msg_handler(1, OSLog_GetBuf)
    def GetBuf(self, msg):
        if self.iobuffer is not None:
            self.log("WARNING: duplicate oslog buffer request")
            return False
        if not msg.SIZE:
            self.log("WARNING: empty oslog buffer request")
            return False

        self.bufsize = msg.SIZE
        if msg.DVA != 0:
            self.iobuffer = self.iobuffer_dva = msg.DVA << 12
            self.log(f"buf prealloc {self.iobuffer:#x} / {self.iobuffer_dva:#x}")
        else:
            self.iobuffer, self.iobuffer_dva = self.asc.ioalloc(align(self.bufsize, 0x4000))
            self.log(f"buf {self.iobuffer:#x} / {self.iobuffer_dva:#x}")
            self.send(OSLog_GetBuf(DVA=self.iobuffer_dva >> 12, SIZE=self.bufsize))

        return True
