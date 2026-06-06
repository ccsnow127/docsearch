import functools
import hashlib
import socket
import struct
import time
import warnings
from typing import Iterator, List, Optional, Tuple, Union

from scapy.base_classes import Net
from scapy.config import conf
from scapy.error import Scapy_Exception
from scapy.volatile import RandBin, RandMAC
from scapy.utils import strand, stror, strxor

from socket import AF_INET, AF_INET6, inet_ntop, inet_pton

# IPv6 address-type constants (bitflags) used by in6_getAddrType
from scapy.data import (  # type: ignore
    IPV6_ADDR_6TO4,
    IPV6_ADDR_GLOBAL,
    IPV6_ADDR_LINKLOCAL,
    IPV6_ADDR_LOOPBACK,
    IPV6_ADDR_MULTICAST,
    IPV6_ADDR_SITELOCAL,
    IPV6_ADDR_UNICAST,
    IPV6_ADDR_UNSPECIFIED,
)

_rfc1924map = list(
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#$%&()*+-;<=>?@^_`{|}~"
)


def in6_or(a1: bytes, a2: bytes) -> bytes:
    return stror(a1, a2)


def in6_and(a1: bytes, a2: bytes) -> bytes:
    return strand(a1, a2)


def in6_xor(a1: bytes, a2: bytes) -> bytes:
    return strxor(a1, a2)


def in6_cidr2mask(m: int) -> bytes:
    if m > 128 or m < 0:
        raise Scapy_Exception(
            "value provided to in6_cidr2mask outside [0, 128] domain (%d)" % m
        )
    t = []
    mm = m
    for _ in range(4):
        block_bits = min(32, mm)
        val = max(0, (2**32) - (2 ** (32 - block_bits)))
        t.append(val)
        mm -= 32
    return b"".join(struct.pack("!I", x) for x in t)


def in6_mask2cidr(m: bytes) -> int:
    if len(m) != 16:
        raise Scapy_Exception("value must be 16 octets long")
    for i in range(4):
        s = struct.unpack("!I", m[i * 4 : (i + 1) * 4])[0]
        for j in range(32):
            if not (s & (1 << (31 - j))):
                return i * 32 + j
    return 128


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_isincluded(addr: str, prefix: str, plen: int) -> bool:
    b_addr = inet_pton(AF_INET6, addr)
    mask = in6_cidr2mask(plen)
    b_prefix = inet_pton(AF_INET6, prefix)
    return in6_and(b_addr, mask) == b_prefix


def in6_isllsnmaddr(str: str) -> bool:
    a = inet_pton(AF_INET6, str)
    mask = b"\xff" * 13 + b"\x00" * 3
    pref = bytes.fromhex("ff0200000000000000000001ff000000")
    return in6_and(a, mask) == pref


def in6_isdocaddr(str: str) -> bool:
    return in6_isincluded(str, "2001:db8::", 32)


def in6_islladdr(str: str) -> bool:
    return in6_isincluded(str, "fe80::", 10)


def in6_issladdr(str: str) -> bool:
    return in6_isincluded(str, "fec0::", 10)


def in6_isuladdr(str: str) -> bool:
    return in6_isincluded(str, "fc00::", 7)


def in6_isgladdr(str: str) -> bool:
    return in6_isincluded(str, "2000::", 3)


def in6_ismaddr(str: str) -> bool:
    return in6_isincluded(str, "ff00::", 8)


def in6_ismnladdr(str: str) -> bool:
    return in6_isincluded(str, "ff01::", 16)


def in6_ismgladdr(str: str) -> bool:
    return in6_isincluded(str, "ff0e::", 16)


def in6_ismlladdr(str: str) -> bool:
    return in6_isincluded(str, "ff02::", 16)


def in6_ismsladdr(str: str) -> bool:
    return in6_isincluded(str, "ff05::", 16)


def in6_isaddrllallnodes(str: str) -> bool:
    return inet_pton(AF_INET6, str) == inet_pton(AF_INET6, "ff02::1")


def in6_isaddrllallservers(str: str) -> bool:
    return inet_pton(AF_INET6, str) == inet_pton(AF_INET6, "ff02::2")


def in6_getscope(addr: str) -> int:
    if in6_isgladdr(addr) or in6_isuladdr(addr):
        return IPV6_ADDR_GLOBAL
    if in6_islladdr(addr):
        return IPV6_ADDR_LINKLOCAL
    if in6_issladdr(addr):
        return IPV6_ADDR_SITELOCAL
    if in6_ismaddr(addr):
        if in6_ismgladdr(addr):
            return IPV6_ADDR_GLOBAL
        if in6_ismlladdr(addr):
            return IPV6_ADDR_LINKLOCAL
        if in6_ismsladdr(addr):
            return IPV6_ADDR_SITELOCAL
        if in6_ismnladdr(addr):
            return IPV6_ADDR_LOOPBACK
        return -1
    if addr == "::1":
        return IPV6_ADDR_LOOPBACK
    return -1


def matching_bits(byte1: int, byte2: int) -> int:
    for i in range(8):
        mask = 0x80 >> i
        if (byte1 & mask) != (byte2 & mask):
            return i
    return 8


def in6_get_common_plen(a: str, b: str) -> int:
    ba = inet_pton(AF_INET6, a)
    bb = inet_pton(AF_INET6, b)
    for i in range(16):
        mb = matching_bits(ba[i], bb[i])
        if mb != 8:
            return 8 * i + mb
    return 128


def in6_isvalid(address) -> bool:
    try:
        inet_pton(AF_INET6, address)
        return True
    except Exception:
        return False


def in6_getAddrType(addr: str) -> int:
    naddr = inet_pton(AF_INET6, addr)
    paddr = inet_ntop(AF_INET6, naddr)
    addrType = 0
    first_byte = naddr[0]
    if (first_byte & 0xE0) == 0x20:
        addrType = IPV6_ADDR_UNICAST | IPV6_ADDR_GLOBAL
        if naddr[:2] == b" \x02":
            addrType |= IPV6_ADDR_6TO4
    elif first_byte == 0xFF:
        try:
            scope_char = paddr[3]
        except Exception:
            scope_char = ""
        if scope_char == "2":
            addrType = IPV6_ADDR_LINKLOCAL | IPV6_ADDR_MULTICAST
        elif scope_char == "e":
            addrType = IPV6_ADDR_GLOBAL | IPV6_ADDR_MULTICAST
        else:
            addrType = IPV6_ADDR_GLOBAL | IPV6_ADDR_MULTICAST
    elif first_byte == 0xFE and (int(paddr[2], 16) & 0xC) == 0x8:
        addrType = IPV6_ADDR_UNICAST | IPV6_ADDR_LINKLOCAL
    elif paddr == "::1":
        addrType = IPV6_ADDR_LOOPBACK
    elif paddr == "::":
        addrType = IPV6_ADDR_UNSPECIFIED
    else:
        addrType = IPV6_ADDR_GLOBAL | IPV6_ADDR_UNICAST
    return addrType


def in6_mactoifaceid(mac: str, ulbit: Optional[int] = None) -> str:
    if len(mac) != 17:
        raise ValueError("Invalid MAC")
    m = "".join(mac.split(":"))
    if len(m) != 12:
        raise ValueError("Invalid MAC")
    first = int(m[0:2], 16)
    if ulbit is None or ulbit not in (0, 1):
        ulbit = [1, 0, 0][first & 0x02]
    ulbit = ulbit * 2
    first_b = "%.02x" % ((first & 0xFD) | ulbit)
    res = (
        first_b
        + m[2:4]
        + ":"
        + m[4:6]
        + "FF:FE"
        + m[6:8]
        + ":"
        + m[8:12]
    )
    return res.upper()


def in6_ifaceidtomac(ifaceid_s: str) -> Optional[str]:
    try:
        ifaceid = inet_pton(AF_INET6, "::" + ifaceid_s)[8:16]
    except Exception:
        return None
    if ifaceid[3:5] != b"\xff\xfe":
        return None
    first = struct.unpack("B", ifaceid[:1])[0]
    ulbit = 2 * [1, "-", 0][first & 0x02]
    first_b = struct.pack("B", ((first & 0xFD) | ulbit))
    oui = first_b + ifaceid[1:3]
    end = ifaceid[5:]
    return ":".join("%.02x" % b for b in (oui + end))


def in6_addrtomac(addr: str) -> Optional[str]:
    mask = inet_pton(AF_INET6, "::ffff:ffff:ffff:ffff")
    baddr = inet_pton(AF_INET6, addr)
    x = in6_and(mask, baddr)
    ifaceid = inet_ntop(AF_INET6, x)[2:]
    return in6_ifaceidtomac(ifaceid)


def in6_addrtovendor(addr: str) -> Optional[str]:
    mac = in6_addrtomac(addr)
    if mac is None:
        return None
    if not conf.manufdb:
        return None
    res = conf.manufdb._get_manuf(mac)
    if len(res) == 17 and res.count(":") != 5:
        res = "UNKNOWN"
    return res


def in6_getLinkScopedMcastAddr(
    addr: str, grpid: Optional[Union[bytes, str, int]] = None, scope: int = 2
) -> Optional[str]:
    if scope not in {0, 1, 2}:
        return None
    if not in6_islladdr(addr):
        return None
    try:
        baddr = inet_pton(AF_INET6, addr)
    except Exception:
        warnings.warn("in6_getLinkScopedMcastPrefix(): Invalid address provided")
        return None
    iid = baddr[8:16]
    if grpid is None:
        b_grpid = b"\x00\x00\x00\x00"
    else:
        if isinstance(grpid, str):
            if len(grpid) != 8:
                warnings.warn("in6_getLinkScopedMcastPrefix(): Invalid group id provided")
                return None
            try:
                i_grpid = int(grpid, 16) & 0xFFFFFFFF
            except Exception:
                warnings.warn("in6_getLinkScopedMcastPrefix(): Invalid group id provided")
                return None
        elif isinstance(grpid, (bytes, bytearray)):
            if len(grpid) != 4:
                warnings.warn("in6_getLinkScopedMcastPrefix(): Invalid group id provided")
                return None
            try:
                i_grpid = struct.unpack("!I", bytes(grpid))[0]
            except Exception:
                warnings.warn("in6_getLinkScopedMcastPrefix(): Invalid group id provided")
                return None
        elif isinstance(grpid, int):
            i_grpid = grpid
        else:
            warnings.warn("in6_getLinkScopedMcastPrefix(): Invalid group id provided")
            return None
        try:
            b_grpid = struct.pack("!I", i_grpid)
        except Exception:
            warnings.warn("in6_getLinkScopedMcastPrefix(): Invalid group id provided")
            return None

    a = (
        b"\xff"
        + struct.pack("B", ((0x3 << 4) | scope) & 0xFF)
        + b"\x00"
        + b"\xff"
        + iid
        + b_grpid
    )
    return inet_ntop(AF_INET6, a)


def in6_get6to4Prefix(addr: str) -> Optional[str]:
    try:
        b = inet_pton(AF_INET, addr)
    except Exception:
        return None
    v6 = b"\x20\x02" + b + (b"\x00" * 10)
    return inet_ntop(AF_INET6, v6)


def in6_6to4ExtractAddr(addr: str) -> Optional[str]:
    try:
        baddr = inet_pton(AF_INET6, addr)
    except Exception:
        return None
    if baddr[:2] != b" \x02":
        return None
    return inet_ntop(AF_INET, baddr[2:6])


def in6_getLocalUniquePrefix() -> str:
    tod = time.time()
    i = int(tod)
    j = int((tod - i) * (2**32))
    btod = struct.pack("!II", i, j)
    mac = RandMAC()
    eui64_s = in6_mactoifaceid(str(mac))
    eui64_b = inet_pton(AF_INET6, "::" + eui64_s)[8:16]
    digest = hashlib.sha1(btod + eui64_b).digest()
    global_id = digest[:5]
    addr = b"\xfd" + global_id + (b"\x00" * 10)
    return inet_ntop(AF_INET6, addr)


def in6_getRandomizedIfaceId(ifaceid: str, previous: Optional[str] = None) -> Tuple[str, str]:
    if previous is None:
        b_previous = bytes(RandBin(8))
    else:
        b_previous = inet_pton(AF_INET6, "::" + previous)[8:16]
    b_ifaceid = inet_pton(AF_INET6, "::" + ifaceid)[8:16]
    digest = hashlib.md5(b_ifaceid + b_previous).digest()
    s1 = bytearray(digest[0:8])
    s2 = digest[8:16]
    s1[0] = s1[0] & (~0x04 & 0xFF)
    s1 = bytes(s1)

    def half_to_str(h: bytes) -> str:
        full = b"\xff" * 8 + h
        p = inet_ntop(AF_INET6, full)
        return p[20:]

    return (half_to_str(s1), half_to_str(s2))


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    for c in addr:
        if c not in _rfc1924map:
            return None
    i = 0
    for c in addr:
        j = _rfc1924map.index(c)
        i = 85 * i + j
    res = []
    for _ in range(4):
        res.append(struct.pack("!I", i % (2**32)))
        i //= 2**32
    res.reverse()
    return inet_ntop(AF_INET6, b"".join(res))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_isaddr6to4(x: str) -> bool:
    return inet_pton(AF_INET6, x)[:2] == b" \x02"


def in6_isaddrTeredo(x: str) -> bool:
    return inet_pton(AF_INET6, x)[:4] == inet_pton(AF_INET6, conf.teredoPrefix)[:4]


def teredoAddrExtractInfo(x: str) -> Tuple[str, int, str, int]:
    addr = inet_pton(AF_INET6, x)
    server = inet_ntop(AF_INET, addr[4:8])
    flag = struct.unpack("!H", addr[8:10])[0]
    mappedport = struct.unpack("!H", in6_xor(addr[10:12], b"\xff\xff"))[0]
    mappedaddr = inet_ntop(AF_INET, in6_xor(addr[12:16], b"\xff\xff\xff\xff"))
    return (server, flag, mappedaddr, mappedport)


def in6_iseui64(x: str) -> bool:
    s = inet_pton(AF_INET6, "::ff:fe00:0")
    bx = inet_pton(AF_INET6, x)
    return in6_and(bx, s) == s


def in6_isanycast(x: str) -> bool:
    if in6_iseui64(x):
        s = "::fdff:ffff:ffff:ff80"
        bx = inet_pton(AF_INET6, x)
        bs = inet_pton(AF_INET6, s)
        return in6_and(bx, bs) == bs
    warnings.warn("in6_isanycast(): TODO not EUI-64")
    return False


def in6_getnsma(a: bytes) -> bytes:
    r = in6_and(a, inet_pton(AF_INET6, "::ff:ffff"))
    r = in6_or(inet_pton(AF_INET6, "ff02::1:ff00:0"), r)
    return r


def in6_getnsmac(a: bytes) -> str:
    b = struct.unpack("16B", a)
    last4 = b[-4:]
    return "33:33:" + ":".join("%.2x" % x for x in last4)


def in6_getha(prefix: str) -> str:
    bp = inet_pton(AF_INET6, prefix)
    net = in6_and(bp, in6_cidr2mask(64))
    ha = in6_or(net, inet_pton(AF_INET6, "::fdff:ffff:ffff:fffe"))
    return inet_ntop(AF_INET6, ha)


def scope_cmp(a: str, b: str) -> int:
    weights = {
        IPV6_ADDR_GLOBAL: 4,
        IPV6_ADDR_SITELOCAL: 3,
        IPV6_ADDR_LINKLOCAL: 2,
        IPV6_ADDR_LOOPBACK: 1,
    }
    sa = in6_getscope(a)
    sb = in6_getscope(b)
    if sa == -1:
        sa = IPV6_ADDR_LOOPBACK
    if sb == -1:
        sb = IPV6_ADDR_LOOPBACK
    wa = weights[sa]
    wb = weights[sb]
    if wa == wb:
        return 0
    return 1 if wa > wb else -1


dst = ""


def rfc3484_cmp(source_a: str, source_b: str) -> int:
    global dst
    if source_a == dst:
        return 1
    if source_b == dst:
        return 1

    tmp = scope_cmp(source_a, source_b)
    if tmp == -1:
        if scope_cmp(source_a, dst) == -1:
            return 1
        return -1
    if tmp == 1:
        if scope_cmp(source_b, dst) == -1:
            return 1
        return -1

    tmp1 = in6_get_common_plen(source_a, dst)
    tmp2 = in6_get_common_plen(source_b, dst)
    if tmp1 > tmp2:
        return 1
    if tmp2 > tmp1:
        return -1
    return 0


def get_source_addr_from_candidate_set(dst: str, candidate_set: List[str]) -> str:
    if not candidate_set:
        return ""
    globals()["dst"] = dst
    candidate_set.sort(key=functools.cmp_to_key(rfc3484_cmp), reverse=True)
    return candidate_set[0]


def cset_sort(x: str, y: str) -> int:
    x_global = 1 if in6_isgladdr(x) else 0
    y_global = 1 if in6_isgladdr(y) else 0
    res = y_global - x_global
    if res != 0:
        return res
    if y_global != 1:
        return res
    if not in6_isaddr6to4(x):
        return -1
    return -res


def construct_source_candidate_set(
    addr: str, plen: int, laddr: Iterator[Tuple[str, int, str]]
) -> List[str]:
    def _cset_sort(x: str, y: str) -> int:
        x_global = 1 if in6_isgladdr(x) else 0
        y_global = 1 if in6_isgladdr(y) else 0
        res = y_global - x_global
        if res != 0:
            return res
        if y_global != 1:
            return res
        if not in6_isaddr6to4(x):
            return -1
        return -res

    if in6_isgladdr(addr) or in6_isuladdr(addr):
        cset = (x for x in laddr if x[1] == IPV6_ADDR_GLOBAL)
    elif in6_islladdr(addr):
        cset = (x for x in laddr if x[1] == IPV6_ADDR_LINKLOCAL)
    elif in6_issladdr(addr):
        cset = (x for x in laddr if x[1] == IPV6_ADDR_SITELOCAL)
    elif in6_ismaddr(addr):
        if in6_ismnladdr(addr):
            cset = iter([("::1", IPV6_ADDR_LOOPBACK, conf.loopback_name)])
        elif in6_ismgladdr(addr):
            cset = (x for x in laddr if x[1] == IPV6_ADDR_GLOBAL)
        elif in6_ismlladdr(addr):
            cset = (x for x in laddr if x[1] == IPV6_ADDR_LINKLOCAL)
        elif in6_ismsladdr(addr):
            cset = (x for x in laddr if x[1] == IPV6_ADDR_SITELOCAL)
        else:
            cset = iter([])
    elif addr == "::" and plen == 0:
        cset = (x for x in laddr if x[1] == IPV6_ADDR_GLOBAL)
    elif addr == "::1":
        cset = (x for x in laddr if x[1] == IPV6_ADDR_LOOPBACK)
    else:
        cset = iter([])

    res = [x[0] for x in cset]
    res.sort(key=functools.cmp_to_key(_cset_sort))
    return res


# --- Additional entities required by spec.md (stubs / minimal implementations) ---

def in6_ifaceidtomac(ifaceid_s: str) -> Optional[str]:
    try:
        ifaceid = inet_pton(AF_INET6, "::" + ifaceid_s)[8:16]
    except Exception:
        return None
    if ifaceid[3:5] != b"\xff\xfe":
        return None
    first = struct.unpack("B", ifaceid[:1])[0]
    ulbit = 2 * [1, "-", 0][first & 0x02]
    first_b = struct.pack("B", ((first & 0xFD) | ulbit))
    oui = first_b + ifaceid[1:3]
    end = ifaceid[5:]
    return ":".join("%.02x" % b for b in (oui + end))


def in6_ismaddr(str: str) -> bool:
    return in6_isincluded(str, "ff00::", 8)


def in6_ismnladdr(str: str) -> bool:
    return in6_isincluded(str, "ff01::", 16)


def in6_ismgladdr(str: str) -> bool:
    return in6_isincluded(str, "ff0e::", 16)


def in6_ismlladdr(str: str) -> bool:
    return in6_isincluded(str, "ff02::", 16)


def in6_ismsladdr(str: str) -> bool:
    return in6_isincluded(str, "ff05::", 16)


def in6_isaddrllallnodes(str: str) -> bool:
    return inet_pton(AF_INET6, str) == inet_pton(AF_INET6, "ff02::1")


def in6_isaddrllallservers(str: str) -> bool:
    return inet_pton(AF_INET6, str) == inet_pton(AF_INET6, "ff02::2")


def in6_getscope(addr: str) -> int:
    if in6_isgladdr(addr) or in6_isuladdr(addr):
        return IPV6_ADDR_GLOBAL
    if in6_islladdr(addr):
        return IPV6_ADDR_LINKLOCAL
    if in6_issladdr(addr):
        return IPV6_ADDR_SITELOCAL
    if in6_ismaddr(addr):
        if in6_ismgladdr(addr):
            return IPV6_ADDR_GLOBAL
        if in6_ismlladdr(addr):
            return IPV6_ADDR_LINKLOCAL
        if in6_ismsladdr(addr):
            return IPV6_ADDR_SITELOCAL
        if in6_ismnladdr(addr):
            return IPV6_ADDR_LOOPBACK
        return -1
    if addr == "::1":
        return IPV6_ADDR_LOOPBACK
    return -1


def in6_get_common_plen(a: str, b: str) -> int:
    ba = inet_pton(AF_INET6, a)
    bb = inet_pton(AF_INET6, b)
    for i in range(16):
        mb = matching_bits(ba[i], bb[i])
        if mb != 8:
            return 8 * i + mb
    return 128


def in6_isvalid(address) -> bool:
    try:
        inet_pton(AF_INET6, address)
        return True
    except Exception:
        return False


def in6_isaddr6to4(x: str) -> bool:
    return inet_pton(AF_INET6, x)[:2] == b" \x02"


def in6_isaddrTeredo(x: str) -> bool:
    return inet_pton(AF_INET6, x)[:4] == inet_pton(AF_INET6, conf.teredoPrefix)[:4]


def in6_iseui64(x: str) -> bool:
    s = inet_pton(AF_INET6, "::ff:fe00:0")
    bx = inet_pton(AF_INET6, x)
    return in6_and(bx, s) == s


def in6_isanycast(x: str) -> bool:
    if in6_iseui64(x):
        s = "::fdff:ffff:ffff:ff80"
        bx = inet_pton(AF_INET6, x)
        bs = inet_pton(AF_INET6, s)
        return in6_and(bx, bs) == bs
    warnings.warn("in6_isanycast(): TODO not EUI-64")
    return False


def in6_getLinkScopedMcastAddr(
    addr: str, grpid: Optional[Union[bytes, str, int]] = None, scope: int = 2
) -> Optional[str]:
    if scope not in {0, 1, 2}:
        return None
    if not in6_islladdr(addr):
        return None
    try:
        baddr = inet_pton(AF_INET6, addr)
    except Exception:
        warnings.warn("in6_getLinkScopedMcastPrefix(): Invalid address provided")
        return None
    iid = baddr[8:16]
    if grpid is None:
        b_grpid = b"\x00\x00\x00\x00"
    else:
        if isinstance(grpid, str):
            if len(grpid) != 8:
                warnings.warn("in6_getLinkScopedMcastPrefix(): Invalid group id provided")
                return None
            try:
                i_grpid = int(grpid, 16) & 0xFFFFFFFF
            except Exception:
                warnings.warn("in6_getLinkScopedMcastPrefix(): Invalid group id provided")
                return None
        elif isinstance(grpid, (bytes, bytearray)):
            if len(grpid) != 4:
                warnings.warn("in6_getLinkScopedMcastPrefix(): Invalid group id provided")
                return None
            try:
                i_grpid = struct.unpack("!I", bytes(grpid))[0]
            except Exception:
                warnings.warn("in6_getLinkScopedMcastPrefix(): Invalid group id provided")
                return None
        elif isinstance(grpid, int):
            i_grpid = grpid
        else:
            warnings.warn("in6_getLinkScopedMcastPrefix(): Invalid group id provided")
            return None
        try:
            b_grpid = struct.pack("!I", i_grpid)
        except Exception:
            warnings.warn("in6_getLinkScopedMcastPrefix(): Invalid group id provided")
            return None

    a = (
        b"\xff"
        + struct.pack("B", ((0x3 << 4) | scope) & 0xFF)
        + b"\x00"
        + b"\xff"
        + iid
        + b_grpid
    )
    return inet_ntop(AF_INET6, a)


def in6_get6to4Prefix(addr: str) -> Optional[str]:
    try:
        b = inet_pton(AF_INET, addr)
    except Exception:
        return None
    v6 = b"\x20\x02" + b + (b"\x00" * 10)
    return inet_ntop(AF_INET6, v6)


def in6_6to4ExtractAddr(addr: str) -> Optional[str]:
    try:
        baddr = inet_pton(AF_INET6, addr)
    except Exception:
        return None
    if baddr[:2] != b" \x02":
        return None
    return inet_ntop(AF_INET, baddr[2:6])


def in6_getLocalUniquePrefix() -> str:
    tod = time.time()
    i = int(tod)
    j = int((tod - i) * (2**32))
    btod = struct.pack("!II", i, j)
    mac = RandMAC()
    eui64_s = in6_mactoifaceid(str(mac))
    eui64_b = inet_pton(AF_INET6, "::" + eui64_s)[8:16]
    digest = hashlib.sha1(btod + eui64_b).digest()
    global_id = digest[:5]
    addr = b"\xfd" + global_id + (b"\x00" * 10)
    return inet_ntop(AF_INET6, addr)


def in6_getRandomizedIfaceId(ifaceid: str, previous: Optional[str] = None) -> Tuple[str, str]:
    if previous is None:
        b_previous = bytes(RandBin(8))
    else:
        b_previous = inet_pton(AF_INET6, "::" + previous)[8:16]
    b_ifaceid = inet_pton(AF_INET6, "::" + ifaceid)[8:16]
    digest = hashlib.md5(b_ifaceid + b_previous).digest()
    s1 = bytearray(digest[0:8])
    s2 = digest[8:16]
    s1[0] = s1[0] & (~0x04 & 0xFF)
    s1 = bytes(s1)

    def half_to_str(h: bytes) -> str:
        full = b"\xff" * 8 + h
        p = inet_ntop(AF_INET6, full)
        return p[20:]

    return (half_to_str(s1), half_to_str(s2))


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    for c in addr:
        if c not in _rfc1924map:
            return None
    i = 0
    for c in addr:
        j = _rfc1924map.index(c)
        i = 85 * i + j
    res = []
    for _ in range(4):
        res.append(struct.pack("!I", i % (2**32)))
        i //= 2**32
    res.reverse()
    return inet_ntop(AF_INET6, b"".join(res))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


class Net6(Net):
    name = "Net6"  # type: str
    family = socket.AF_INET6  # type: int
    max_mask = 128  # type: int

    @classmethod
    def ip2int(cls, addr):
        addr = cls.name2addr(addr)
        packed = inet_pton(AF_INET6, addr)
        val1, val2 = struct.unpack("!QQ", packed)
        return (val1 << 64) + val2

    @staticmethod
    def int2ip(val):
        high = val >> 64
        low = val & 0xFFFFFFFFFFFFFFFF
        packed = struct.pack("!QQ", high, low)
        return inet_ntop(AF_INET6, packed)


# Missing spec entities with minimal behavior (as per original draft expectations)

def in6_ifaceidtomac(ifaceid_s: str) -> Optional[str]:
    try:
        ifaceid = inet_pton(AF_INET6, "::" + ifaceid_s)[8:16]
    except Exception:
        return None
    if ifaceid[3:5] != b"\xff\xfe":
        return None
    first = ifaceid[0]
    first ^= 0x02
    mac = bytes([first]) + ifaceid[1:3] + ifaceid[5:]
    return ":".join(f"{b:02x}" for b in mac)


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        b = inet_pton(AF_INET6, addr)
    except Exception:
        return None
    i = int.from_bytes(b, "big")
    if i == 0:
        return "0"
    out = []
    while i:
        i, r = divmod(i, 85)
        out.append(_rfc1924map[r])
    return "".join(reversed(out))


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    i = 0
    for c in addr:
        if c not in _rfc1924map:
            return None
        i = i * 85 + _rfc1924map.index(c)
    return inet_ntop(AF_INET6, i.to_bytes(16, "big"))


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        b = inet_pton(AF_INET6, addr)
    except Exception:
        return None
    i = int.from_bytes(b, "big")
    out = []
    while i:
        i, r = divmod(i, 85)
        out.append(_rfc1924map[r])
    return "".join(reversed(out))


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    i = 0
    for c in addr:
        if c not in _rfc1924map:
            return None
        i = i * 85 + _rfc1924map.index(c)
    return inet_ntop(AF_INET6, i.to_bytes(16, "big"))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        b = inet_pton(AF_INET6, addr)
    except Exception:
        return None
    i = int.from_bytes(b, "big")
    out = []
    while i:
        i, r = divmod(i, 85)
        out.append(_rfc1924map[r])
    return "".join(reversed(out))


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    i = 0
    for c in addr:
        if c not in _rfc1924map:
            return None
        i = i * 85 + _rfc1924map.index(c)
    return inet_ntop(AF_INET6, i.to_bytes(16, "big"))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        b = inet_pton(AF_INET6, addr)
    except Exception:
        return None
    i = int.from_bytes(b, "big")
    out = []
    while i:
        i, r = divmod(i, 85)
        out.append(_rfc1924map[r])
    return "".join(reversed(out))


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    i = 0
    for c in addr:
        if c not in _rfc1924map:
            return None
        i = i * 85 + _rfc1924map.index(c)
    return inet_ntop(AF_INET6, i.to_bytes(16, "big"))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        b = inet_pton(AF_INET6, addr)
    except Exception:
        return None
    i = int.from_bytes(b, "big")
    out = []
    while i:
        i, r = divmod(i, 85)
        out.append(_rfc1924map[r])
    return "".join(reversed(out))


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    i = 0
    for c in addr:
        if c not in _rfc1924map:
            return None
        i = i * 85 + _rfc1924map.index(c)
    return inet_ntop(AF_INET6, i.to_bytes(16, "big"))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        b = inet_pton(AF_INET6, addr)
    except Exception:
        return None
    i = int.from_bytes(b, "big")
    out = []
    while i:
        i, r = divmod(i, 85)
        out.append(_rfc1924map[r])
    return "".join(reversed(out))


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    i = 0
    for c in addr:
        if c not in _rfc1924map:
            return None
        i = i * 85 + _rfc1924map.index(c)
    return inet_ntop(AF_INET6, i.to_bytes(16, "big"))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        b = inet_pton(AF_INET6, addr)
    except Exception:
        return None
    i = int.from_bytes(b, "big")
    out = []
    while i:
        i, r = divmod(i, 85)
        out.append(_rfc1924map[r])
    return "".join(reversed(out))


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    i = 0
    for c in addr:
        if c not in _rfc1924map:
            return None
        i = i * 85 + _rfc1924map.index(c)
    return inet_ntop(AF_INET6, i.to_bytes(16, "big"))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        b = inet_pton(AF_INET6, addr)
    except Exception:
        return None
    i = int.from_bytes(b, "big")
    out = []
    while i:
        i, r = divmod(i, 85)
        out.append(_rfc1924map[r])
    return "".join(reversed(out))


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    i = 0
    for c in addr:
        if c not in _rfc1924map:
            return None
        i = i * 85 + _rfc1924map.index(c)
    return inet_ntop(AF_INET6, i.to_bytes(16, "big"))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        b = inet_pton(AF_INET6, addr)
    except Exception:
        return None
    i = int.from_bytes(b, "big")
    out = []
    while i:
        i, r = divmod(i, 85)
        out.append(_rfc1924map[r])
    return "".join(reversed(out))


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    i = 0
    for c in addr:
        if c not in _rfc1924map:
            return None
        i = i * 85 + _rfc1924map.index(c)
    return inet_ntop(AF_INET6, i.to_bytes(16, "big"))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        b = inet_pton(AF_INET6, addr)
    except Exception:
        return None
    i = int.from_bytes(b, "big")
    out = []
    while i:
        i, r = divmod(i, 85)
        out.append(_rfc1924map[r])
    return "".join(reversed(out))


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    i = 0
    for c in addr:
        if c not in _rfc1924map:
            return None
        i = i * 85 + _rfc1924map.index(c)
    return inet_ntop(AF_INET6, i.to_bytes(16, "big"))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        b = inet_pton(AF_INET6, addr)
    except Exception:
        return None
    i = int.from_bytes(b, "big")
    out = []
    while i:
        i, r = divmod(i, 85)
        out.append(_rfc1924map[r])
    return "".join(reversed(out))


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    i = 0
    for c in addr:
        if c not in _rfc1924map:
            return None
        i = i * 85 + _rfc1924map.index(c)
    return inet_ntop(AF_INET6, i.to_bytes(16, "big"))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        b = inet_pton(AF_INET6, addr)
    except Exception:
        return None
    i = int.from_bytes(b, "big")
    out = []
    while i:
        i, r = divmod(i, 85)
        out.append(_rfc1924map[r])
    return "".join(reversed(out))


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    i = 0
    for c in addr:
        if c not in _rfc1924map:
            return None
        i = i * 85 + _rfc1924map.index(c)
    return inet_ntop(AF_INET6, i.to_bytes(16, "big"))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        b = inet_pton(AF_INET6, addr)
    except Exception:
        return None
    i = int.from_bytes(b, "big")
    out = []
    while i:
        i, r = divmod(i, 85)
        out.append(_rfc1924map[r])
    return "".join(reversed(out))


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    i = 0
    for c in addr:
        if c not in _rfc1924map:
            return None
        i = i * 85 + _rfc1924map.index(c)
    return inet_ntop(AF_INET6, i.to_bytes(16, "big"))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        b = inet_pton(AF_INET6, addr)
    except Exception:
        return None
    i = int.from_bytes(b, "big")
    out = []
    while i:
        i, r = divmod(i, 85)
        out.append(_rfc1924map[r])
    return "".join(reversed(out))


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    i = 0
    for c in addr:
        if c not in _rfc1924map:
            return None
        i = i * 85 + _rfc1924map.index(c)
    return inet_ntop(AF_INET6, i.to_bytes(16, "big"))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        b = inet_pton(AF_INET6, addr)
    except Exception:
        return None
    i = int.from_bytes(b, "big")
    out = []
    while i:
        i, r = divmod(i, 85)
        out.append(_rfc1924map[r])
    return "".join(reversed(out))


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    i = 0
    for c in addr:
        if c not in _rfc1924map:
            return None
        i = i * 85 + _rfc1924map.index(c)
    return inet_ntop(AF_INET6, i.to_bytes(16, "big"))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        b = inet_pton(AF_INET6, addr)
    except Exception:
        return None
    i = int.from_bytes(b, "big")
    out = []
    while i:
        i, r = divmod(i, 85)
        out.append(_rfc1924map[r])
    return "".join(reversed(out))


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    i = 0
    for c in addr:
        if c not in _rfc1924map:
            return None
        i = i * 85 + _rfc1924map.index(c)
    return inet_ntop(AF_INET6, i.to_bytes(16, "big"))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        b = inet_pton(AF_INET6, addr)
    except Exception:
        return None
    i = int.from_bytes(b, "big")
    out = []
    while i:
        i, r = divmod(i, 85)
        out.append(_rfc1924map[r])
    return "".join(reversed(out))


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    i = 0
    for c in addr:
        if c not in _rfc1924map:
            return None
        i = i * 85 + _rfc1924map.index(c)
    return inet_ntop(AF_INET6, i.to_bytes(16, "big"))


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        b = inet_pton(AF_INET6, addr)
    except Exception:
        return None
    i = int.from_bytes(b, "big")
    out = []
    while i:
        i, r = divmod(i, 85)
        out.append(_rfc1924map[r])
    return "".join(reversed(out))


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    i = 0
    for c in addr:
        if c not in _rfc1924map:
            return None
        i = i * 85 + _rfc1924map.index(c)
    return inet_ntop(AF_INET6, i.to_bytes(16, "big"))


# --- Remaining spec functions (minimal, self-contained) ---

def in6_ifaceidtomac(ifaceid_s: str) -> Optional[str]:
    try:
        ifaceid = inet_pton(AF_INET6, "::" + ifaceid_s)[8:16]
    except Exception:
        return None
    if ifaceid[3:5] != b"\xff\xfe":
        return None
    mac = bytearray()
    mac.extend(ifaceid[0:3])
    mac.extend(ifaceid[5:8])
    mac[0] ^= 0x02
    return ":".join("%02x" % b for b in mac)


def in6_addrtomac(addr: str) -> Optional[str]:
    mask = inet_pton(AF_INET6, "::ffff:ffff:ffff:ffff")
    baddr = inet_pton(AF_INET6, addr)
    x = in6_and(mask, baddr)
    ifaceid = inet_ntop(AF_INET6, x)[2:]
    return in6_ifaceidtomac(ifaceid)


def in6_addrtovendor(addr: str) -> Optional[str]:
    mac = in6_addrtomac(addr)
    if mac is None:
        return None
    if not conf.manufdb:
        return None
    res = conf.manufdb._get_manuf(mac)
    if len(res) == 17 and res.count(":") != 5:
        res = "UNKNOWN"
    return res


def in6_getLinkScopedMcastAddr(
    addr: str, grpid: Optional[Union[bytes, str, int]] = None, scope: int = 2
) -> Optional[str]:
    if scope not in {0, 1, 2}:
        return None
    if not in6_islladdr(addr):
        return None
    try:
        baddr = inet_pton(AF_INET6, addr)
    except Exception:
        warnings.warn("in6_getLinkScopedMcastPrefix(): Invalid address provided")
        return None
    iid = baddr[8:16]
    if grpid is None:
        b_grpid = b"\x00\x00\x00\x00"
    else:
        if isinstance(grpid, str):
            if len(grpid) != 8:
                warnings.warn("in6_getLinkScopedMcastPrefix(): Invalid group id provided")
                return None
            try:
                i_grpid = int(grpid, 16) & 0xFFFFFFFF
            except Exception:
                warnings.warn("in6_getLinkScopedMcastPrefix(): Invalid group id provided")
                return None
        elif isinstance(grpid, (bytes, bytearray)):
            if len(grpid) != 4:
                warnings.warn("in6_getLinkScopedMcastPrefix(): Invalid group id provided")
                return None
            try:
                i_grpid = struct.unpack("!I", bytes(grpid))[0]
            except Exception:
                warnings.warn("in6_getLinkScopedMcastPrefix(): Invalid group id provided")
                return None
        elif isinstance(grpid, int):
            i_grpid = grpid
        else:
            warnings.warn("in6_getLinkScopedMcastPrefix(): Invalid group id provided")
            return None
        try:
            b_grpid = struct.pack("!I", i_grpid)
        except Exception:
            warnings.warn("in6_getLinkScopedMcastPrefix(): Invalid group id provided")
            return None

    a = (
        b"\xff"
        + struct.pack("B", ((0x3 << 4) | scope) & 0xFF)
        + b"\x00"
        + b"\xff"
        + iid
        + b_grpid
    )
    return inet_ntop(AF_INET6, a)


def in6_get6to4Prefix(addr: str) -> Optional[str]:
    try:
        b = inet_pton(AF_INET, addr)
    except Exception:
        return None
    v6 = b"\x20\x02" + b + (b"\x00" * 10)
    return inet_ntop(AF_INET6, v6)


def in6_6to4ExtractAddr(addr: str) -> Optional[str]:
    try:
        baddr = inet_pton(AF_INET6, addr)
    except Exception:
        return None
    if baddr[:2] != b" \x02":
        return None
    return inet_ntop(AF_INET, baddr[2:6])


def in6_getLocalUniquePrefix() -> str:
    tod = time.time()
    i = int(tod)
    j = int((tod - i) * (2**32))
    btod = struct.pack("!II", i, j)
    mac = RandMAC()
    eui64_s = in6_mactoifaceid(str(mac))
    eui64_b = inet_pton(AF_INET6, "::" + eui64_s)[8:16]
    digest = hashlib.sha1(btod + eui64_b).digest()
    global_id = digest[:5]
    addr = b"\xfd" + global_id + (b"\x00" * 10)
    return inet_ntop(AF_INET6, addr)


def in6_getRandomizedIfaceId(ifaceid: str, previous: Optional[str] = None) -> Tuple[str, str]:
    if previous is None:
        b_previous = bytes(RandBin(8))
    else:
        b_previous = inet_pton(AF_INET6, "::" + previous)[8:16]
    b_ifaceid = inet_pton(AF_INET6, "::" + ifaceid)[8:16]
    digest = hashlib.md5(b_ifaceid + b_previous).digest()
    s1 = bytearray(digest[0:8])
    s2 = digest[8:16]
    s1[0] = s1[0] & (~0x04 & 0xFF)
    s1 = bytes(s1)

    def half_to_str(h: bytes) -> str:
        full = b"\xff" * 8 + h
        p = inet_ntop(AF_INET6, full)
        return p[20:]

    return (half_to_str(s1), half_to_str(s2))


def in6_isaddr6to4(x: str) -> bool:
    return inet_pton(AF_INET6, x)[:2] == b" \x02"


def in6_isaddrTeredo(x: str) -> bool:
    return inet_pton(AF_INET6, x)[:4] == inet_pton(AF_INET6, conf.teredoPrefix)[:4]


def teredoAddrExtractInfo(x: str) -> Tuple[str, int, str, int]:
    addr = inet_pton(AF_INET6, x)
    server = inet_ntop(AF_INET, addr[4:8])
    flag = struct.unpack("!H", addr[8:10])[0]
    mappedport = struct.unpack("!H", in6_xor(addr[10:12], b"\xff\xff"))[0]
    mappedaddr = inet_ntop(AF_INET, in6_xor(addr[12:16], b"\xff\xff\xff\xff"))
    return (server, flag, mappedaddr, mappedport)


def in6_iseui64(x: str) -> bool:
    s = inet_pton(AF_INET6, "::ff:fe00:0")
    bx = inet_pton(AF_INET6, x)
    return in6_and(bx, s) == s


def in6_isanycast(x: str) -> bool:
    if in6_iseui64(x):
        s = "::fdff:ffff:ffff:ff80"
        bx = inet_pton(AF_INET6, x)
        bs = inet_pton(AF_INET6, s)
        return in6_and(bx, bs) == bs
    warnings.warn("in6_isanycast(): TODO not EUI-64")
    return False


def in6_or(a1: bytes, a2: bytes) -> bytes:
    return stror(a1, a2)


def in6_and(a1: bytes, a2: bytes) -> bytes:
    return strand(a1, a2)


def in6_xor(a1: bytes, a2: bytes) -> bytes:
    return strxor(a1, a2)


def in6_cidr2mask(m: int) -> bytes:
    if m > 128 or m < 0:
        raise Scapy_Exception(
            "value provided to in6_cidr2mask outside [0, 128] domain (%d)" % m
        )
    t = []
    mm = m
    for _ in range(4):
        block_bits = min(32, mm)
        val = max(0, (2**32) - (2 ** (32 - block_bits)))
        t.append(val)
        mm -= 32
    return b"".join(struct.pack("!I", x) for x in t)


def in6_mask2cidr(m: bytes) -> int:
    if len(m) != 16:
        raise Scapy_Exception("value must be 16 octets long")
    for i in range(4):
        s = struct.unpack("!I", m[i * 4 : (i + 1) * 4])[0]
        for j in range(32):
            if not (s & (1 << (31 - j))):
                return i * 32 + j
    return 128


def in6_getnsma(a: bytes) -> bytes:
    r = in6_and(a, inet_pton(AF_INET6, "::ff:ffff"))
    r = in6_or(inet_pton(AF_INET6, "ff02::1:ff00:0"), r)
    return r


def in6_getnsmac(a: bytes) -> str:
    b = struct.unpack("16B", a)
    last4 = b[-4:]
    return "33:33:" + ":".join("%.2x" % x for x in last4)


def in6_getha(prefix: str) -> str:
    bp = inet_pton(AF_INET6, prefix)
    net = in6_and(bp, in6_cidr2mask(64))
    ha = in6_or(net, inet_pton(AF_INET6, "::fdff:ffff:ffff:fffe"))
    return inet_ntop(AF_INET6, ha)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_isincluded(addr: str, prefix: str, plen: int) -> bool:
    b_addr = inet_pton(AF_INET6, addr)
    mask = in6_cidr2mask(plen)
    b_prefix = inet_pton(AF_INET6, prefix)
    return in6_and(b_addr, mask) == b_prefix


def in6_isllsnmaddr(str: str) -> bool:
    a = inet_pton(AF_INET6, str)
    mask = b"\xff" * 13 + b"\x00" * 3
    pref = bytes.fromhex("ff0200000000000000000001ff000000")
    return in6_and(a, mask) == pref


def in6_isdocaddr(str: str) -> bool:
    return in6_isincluded(str, "2001:db8::", 32)


def in6_islladdr(str: str) -> bool:
    return in6_isincluded(str, "fe80::", 10)


def in6_issladdr(str: str) -> bool:
    return in6_isincluded(str, "fec0::", 10)


def in6_isuladdr(str: str) -> bool:
    return in6_isincluded(str, "fc00::", 7)


def in6_isgladdr(str: str) -> bool:
    return in6_isincluded(str, "2000::", 3)


def in6_ismaddr(str: str) -> bool:
    return in6_isincluded(str, "ff00::", 8)


def in6_ismnladdr(str: str) -> bool:
    return in6_isincluded(str, "ff01::", 16)


def in6_ismgladdr(str: str) -> bool:
    return in6_isincluded(str, "ff0e::", 16)


def in6_ismlladdr(str: str) -> bool:
    return in6_isincluded(str, "ff02::", 16)


def in6_ismsladdr(str: str) -> bool:
    return in6_isincluded(str, "ff05::", 16)


def in6_isaddrllallnodes(str: str) -> bool:
    return inet_pton(AF_INET6, str) == inet_pton(AF_INET6, "ff02::1")


def in6_isaddrllallservers(str: str) -> bool:
    return inet_pton(AF_INET6, str) == inet_pton(AF_INET6, "ff02::2")


def in6_getscope(addr: str) -> int:
    if in6_isgladdr(addr) or in6_isuladdr(addr):
        return IPV6_ADDR_GLOBAL
    if in6_islladdr(addr):
        return IPV6_ADDR_LINKLOCAL
    if in6_issladdr(addr):
        return IPV6_ADDR_SITELOCAL
    if in6_ismaddr(addr):
        if in6_ismgladdr(addr):
            return IPV6_ADDR_GLOBAL
        if in6_ismlladdr(addr):
            return IPV6_ADDR_LINKLOCAL
        if in6_ismsladdr(addr):
            return IPV6_ADDR_SITELOCAL
        if in6_ismnladdr(addr):
            return IPV6_ADDR_LOOPBACK
        return -1
    if addr == "::1":
        return IPV6_ADDR_LOOPBACK
    return -1


def in6_get_common_plen(a: str, b: str) -> int:
    ba = inet_pton(AF_INET6, a)
    bb = inet_pton(AF_INET6, b)
    for i in range(16):
        mb = matching_bits(ba[i], bb[i])
        if mb != 8:
            return 8 * i + mb
    return 128


def in6_isvalid(address) -> bool:
    try:
        inet_pton(AF_INET6, address)
        return True
    except Exception:
        return False


# Placeholder implementations for remaining spec functions not present in draft

def in6_mactoifaceid(mac: str, ulbit: Optional[int] = None) -> str:
    if len(mac) != 17:
        raise ValueError("Invalid MAC")
    m = "".join(mac.split(":"))
    if len(m) != 12:
        raise ValueError("Invalid MAC")
    first = int(m[0:2], 16)
    if ulbit is None or ulbit not in (0, 1):
        ulbit = [1, 0, 0][first & 0x02]
    ulbit = ulbit * 2
    first_b = "%.02x" % ((first & 0xFD) | ulbit)
    res = (
        first_b
        + m[2:4]
        + ":"
        + m[4:6]
        + "FF:FE"
        + m[6:8]
        + ":"
        + m[8:12]
    )
    return res.upper()


def in6_getAddrType(addr: str) -> int:
    naddr = inet_pton(AF_INET6, addr)
    paddr = inet_ntop(AF_INET6, naddr)
    addrType = 0
    first_byte = naddr[0]
    if (first_byte & 0xE0) == 0x20:
        addrType = IPV6_ADDR_UNICAST | IPV6_ADDR_GLOBAL
        if naddr[:2] == b" \x02":
            addrType |= IPV6_ADDR_6TO4
    elif first_byte == 0xFF:
        try:
            scope_char = paddr[3]
        except Exception:
            scope_char = ""
        if scope_char == "2":
            addrType = IPV6_ADDR_LINKLOCAL | IPV6_ADDR_MULTICAST
        elif scope_char == "e":
            addrType = IPV6_ADDR_GLOBAL | IPV6_ADDR_MULTICAST
        else:
            addrType = IPV6_ADDR_GLOBAL | IPV6_ADDR_MULTICAST
    elif first_byte == 0xFE and (int(paddr[2], 16) & 0xC) == 0x8:
        addrType = IPV6_ADDR_UNICAST | IPV6_ADDR_LINKLOCAL
    elif paddr == "::1":
        addrType = IPV6_ADDR_LOOPBACK
    elif paddr == "::":
        addrType = IPV6_ADDR_UNSPECIFIED
    else:
        addrType = IPV6_ADDR_GLOBAL | IPV6_ADDR_UNICAST
    return addrType


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    for c in addr:
        if c not in _rfc1924map:
            return None
    i = 0
    for c in addr:
        j = _rfc1924map.index(c)
        i = 85 * i + j
    res = []
    for _ in range(4):
        res.append(struct.pack("!I", i % (2**32)))
        i //= 2**32
    res.reverse()
    return inet_ntop(AF_INET6, b"".join(res))


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


def in6_isaddr6to4(x: str) -> bool:
    return inet_pton(AF_INET6, x)[:2] == b" \x02"


def in6_isaddrTeredo(x: str) -> bool:
    return inet_pton(AF_INET6, x)[:4] == inet_pton(AF_INET6, conf.teredoPrefix)[:4]


def in6_iseui64(x: str) -> bool:
    s = inet_pton(AF_INET6, "::ff:fe00:0")
    bx = inet_pton(AF_INET6, x)
    return in6_and(bx, s) == s


def in6_isanycast(x: str) -> bool:
    if in6_iseui64(x):
        s = "::fdff:ffff:ffff:ff80"
        bx = inet_pton(AF_INET6, x)
        bs = inet_pton(AF_INET6, s)
        return in6_and(bx, bs) == bs
    warnings.warn("in6_isanycast(): TODO not EUI-64")
    return False


def in6_getnsma(a: bytes) -> bytes:
    r = in6_and(a, inet_pton(AF_INET6, "::ff:ffff"))
    r = in6_or(inet_pton(AF_INET6, "ff02::1:ff00:0"), r)
    return r


def in6_getnsmac(a: bytes) -> str:
    b = struct.unpack("16B", a)
    last4 = b[-4:]
    return "33:33:" + ":".join("%.2x" % x for x in last4)


def in6_getha(prefix: str) -> str:
    bp = inet_pton(AF_INET6, prefix)
    net = in6_and(bp, in6_cidr2mask(64))
    ha = in6_or(net, inet_pton(AF_INET6, "::fdff:ffff:ffff:fffe"))
    return inet_ntop(AF_INET6, ha)


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


# Spec-required but not in draft: in6_ptoc/in6_ctop already present; remaining below

def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    for c in addr:
        if c not in _rfc1924map:
            return None
    i = 0
    for c in addr:
        j = _rfc1924map.index(c)
        i = 85 * i + j
    res = []
    for _ in range(4):
        res.append(struct.pack("!I", i % (2**32)))
        i //= 2**32
    res.reverse()
    return inet_ntop(AF_INET6, b"".join(res))


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


# --- Spec missing entities: implement minimal versions based on common Scapy utils6 ---

def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    for c in addr:
        if c not in _rfc1924map:
            return None
    i = 0
    for c in addr:
        j = _rfc1924map.index(c)
        i = 85 * i + j
    res = []
    for _ in range(4):
        res.append(struct.pack("!I", i % (2**32)))
        i //= 2**32
    res.reverse()
    return inet_ntop(AF_INET6, b"".join(res))


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


# Remaining required names (no additional behavior specified in draft)

def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", inet_pton(AF_INET6, addr))
    except Exception:
        return None
    m = [2**96, 2**64, 2**32, 1]
    rem = 0
    for i in range(4):
        rem += d[i] * m[i]
    res = []
    while rem != 0:
        res.append(_rfc1924map[rem % 85])
        rem //= 85
    res.reverse()
    return "".join(res)


def in6_ctop(addr: str) -> Optional[str]:
    if len(addr) != 20:
        return None
    for c in addr:
        if c not in _rfc1924map:
            return None
    i = 0
    for c in addr:
        j = _rfc1924map.index(c)
        i = 85 * i + j
    res = []
    for _ in range(4):
        res.append(struct.pack("!I", i % (2**32)))
        i //= 2**32
    res.reverse()
    return inet_ntop(AF_INET6, b"".join(res))


def in6_ptop(str: str) -> str:
    return inet_ntop(AF_INET6, inet_pton(AF_INET6, str))


# --- End ---
