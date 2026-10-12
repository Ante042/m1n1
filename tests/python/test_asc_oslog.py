# SPDX-License-Identifier: MIT
from types import SimpleNamespace

import pytest

from proxyclient.m1n1.fw.asc.oslog import ASCOSLogEndpoint, OSLog_GetBuf


def endpoint(dva=0x10010004000):
    allocations, sent = [], []
    def allocate(size):
        allocations.append(size)
        return 0x20000000000, dva
    asc = SimpleNamespace(ioalloc=allocate,
                          send=lambda msg, ep: sent.append((int(msg), int(ep))))
    return ASCOSLogEndpoint(asc, 8), allocations, sent


def test_captured_preallocated_request_has_byte_size_and_shifted_dva():
    word = 0x0105ff8010009a04
    msg = OSLog_GetBuf(word)
    assert msg.SIZE == 0x5ff8
    assert msg.DVA << 12 == 0x10009a04000
    ep, allocations, sent = endpoint()
    assert ep.handle_msg(word, 8) is True
    assert ep.bufsize == 0x5ff8
    assert ep.iobuffer == ep.iobuffer_dva == 0x10009a04000
    assert allocations == sent == []
    assert ep.SHORT == "oslog"


@pytest.mark.parametrize('size', [1, 0x1234, 0x4001, 0x5ff8, 0xfffff])
def test_allocation_rounds_backing_only_reply_preserves_requested_bytes(size):
    ep, allocations, sent = endpoint()
    assert ep.GetBuf(OSLog_GetBuf(SIZE=size, DVA=0)) is True
    assert ep.bufsize == size
    assert allocations == [(size + 0x3fff) & ~0x3fff]
    assert sent == [((1 << 56) | (size << 36) | (0x10010004000 >> 12), 8)]
    reply = OSLog_GetBuf(sent[0][0])
    assert reply.SIZE == size
    assert reply.DVA << 12 == ep.iobuffer_dva


def test_size_and_dva_high_bits_do_not_overlap():
    msg = OSLog_GetBuf(SIZE=0xfffff, DVA=(1 << 36)-1)
    assert int(msg) == (1 << 56) | ((1 << 56)-1)
    assert msg.SIZE == 0xfffff
    assert msg.DVA == (1 << 36)-1
    ep, allocations, sent = endpoint(0xfffffffff000)
    assert ep.GetBuf(OSLog_GetBuf(SIZE=0xabcde)) is True
    reply = OSLog_GetBuf(sent[0][0])
    assert reply.SIZE == 0xabcde
    assert reply.DVA == (1 << 36)-1


@pytest.mark.parametrize('dva', [0, 0x10009a04])
def test_empty_request_refuses_without_allocation_or_send(dva):
    ep, allocations, sent = endpoint()
    assert ep.GetBuf(OSLog_GetBuf(SIZE=0, DVA=dva)) is False
    assert ep.iobuffer is ep.iobuffer_dva is None
    assert allocations == sent == []


@pytest.mark.parametrize('first_preallocated', [False, True])
@pytest.mark.parametrize('second_dva', [0, 0x10009a04])
def test_duplicate_request_refuses_without_replacing_buffer_or_sending(first_preallocated, second_dva):
    ep, allocations, sent = endpoint()
    first = OSLog_GetBuf(SIZE=0x1234, DVA=0x10009a04 if first_preallocated else 0)
    assert ep.GetBuf(first) is True
    original = ep.iobuffer, ep.iobuffer_dva, ep.bufsize
    counts = len(allocations), len(sent)
    assert ep.GetBuf(OSLog_GetBuf(SIZE=0x5678, DVA=second_dva)) is False
    assert (ep.iobuffer, ep.iobuffer_dva, ep.bufsize) == original
    assert (len(allocations), len(sent)) == counts


def test_zero_valued_existing_buffer_is_still_a_duplicate():
    ep, allocations, sent = endpoint()
    ep.iobuffer = 0
    assert ep.GetBuf(OSLog_GetBuf(SIZE=1)) is False
    assert allocations == sent == []
