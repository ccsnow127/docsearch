import functools
import hashlib
import socket
import struct
import time
import warnings
from typing import Iterator, List, Optional, Tuple, Union

try:
    from scapy.base_classes import Net  # type: ignore
except Exception:  # pragma: no cover
    class Net:  # minimal fallback
        name = "Net"
        family = socket.AF_INET
        max_mask = 32

        @classmethod
        def name2addr(cls, addr: str) -> str:
            return addr


try:
    from scapy.config import conf  # type: ignore
except Exception:  # pragma: no cover
    class _DummyConf:
        loopback_name = "lo"
        teredoPrefix = "2001::"
        manufdb = None

    conf = _DummyConf()  # type: ignore


try:
    from scapy.data import (  # type: ignore
        IPV6_ADDR_UNICAST,
        IPV6_ADDR_MULTICAST,
        IPV6_ADDR_GLOBAL,
        IPV6_ADDR_LINKLOCAL,
        IPV6_ADDR_SITELOCAL,
        IPV6_ADDR_LOOPBACK,
        IPV6_ADDR_UNSPECIFIED,
        IPV6_ADDR_6TO4,
    )
except Exception:  # pragma: no cover
    IPV6_ADDR_UNICAST = 0x01
    IPV6_ADDR_MULTICAST = 0x02
    IPV6_ADDR_GLOBAL = 0x04
    IPV6_ADDR_LINKLOCAL = 0x08
    IPV6_ADDR_LOOPBACK = 0x10
    IPV6_ADDR_UNSPECIFIED = 0x20
    IPV6_ADDR_6TO4 = 0x40
    IPV6_ADDR_SITELOCAL = 0x100  # best-effort fallback; scapy value may differ


try:
    from scapy.error import Scapy_Exception  # type: ignore
except Exception:  # pragma: no cover
    class Scapy_Exception(Exception):
        pass


try:
    from scapy.utils import strand as _strand, stror as _stror, strxor as _strxor  # type: ignore
except Exception:  # pragma: no cover
    def _strand(a: bytes, b: bytes) -> bytes:
        return bytes((x & y) for x, y in zip(a, b))

    def _stror(a: bytes, b: bytes) -> bytes:
        return bytes((x | y) for x, y in zip(a, b))

    def _strxor(a: bytes, b: bytes) -> bytes:
        return bytes((x ^ y) for x, y in zip(a, b))


try:
    from scapy.volatile import RandMAC, RandBin  # type: ignore
except Exception:  # pragma: no cover
    import os

    class RandMAC:
        def __str__(self) -> str:
            b = os.urandom(6)
            return ":".join(f"{x:02x}" for x in b)

    class RandBin:
        def __init__(self, n: int):
            self.n = n

        def __bytes__(self) -> bytes:
            return os.urandom(self.n)


_rfc1924map = list("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#$%&()*+-;<=>?@^_`{|}~")


def in6_or(a1: bytes, a2: bytes) -> bytes:
    return _stror(a1, a2)


def in6_and(a1: bytes, a2: bytes) -> bytes:
    return _strand(a1, a2)


def in6_xor(a1: bytes, a2: bytes) -> bytes:
    return _strxor(a1, a2)


def in6_ptop(str: str) -> str:
    return socket.inet_ntop(socket.AF_INET6, socket.inet_pton(socket.AF_INET6, str))


def in6_cidr2mask(m: int) -> bytes:
    if m > 128 or m < 0:
        raise Scapy_Exception("value provided to in6_cidr2mask outside [0, 128] domain (%d)" % m)
    t = []
    for _ in range(4):
        block_bits = min(32, m)
        val = max(0, 2**32 - 2 ** (32 - block_bits)) if block_bits != 0 else 0
        t.append(val)
        m -= 32
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


def in6_isincluded(addr: str, prefix: str, plen: int) -> bool:
    b_addr = socket.inet_pton(socket.AF_INET6, addr)
    mask = in6_cidr2mask(plen)
    b_prefix = socket.inet_pton(socket.AF_INET6, prefix)
    return in6_and(b_addr, mask) == b_prefix


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
    return socket.inet_pton(socket.AF_INET6, str) == socket.inet_pton(socket.AF_INET6, "ff02::1")


def in6_isaddrllallservers(str: str) -> bool:
    return socket.inet_pton(socket.AF_INET6, str) == socket.inet_pton(socket.AF_INET6, "ff02::2")


def in6_isllsnmaddr(str: str) -> bool:
    a = socket.inet_pton(socket.AF_INET6, str)
    mask = b"\xff" * 13 + b"\x00" * 3
    masked = in6_and(a, mask)
    const = bytes.fromhex("ff0200000000000000000001ff000000")
    return masked == const


def in6_getscope(addr) -> int:
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


def scope_cmp(a: str, b: str) -> int:
    weights = {
        IPV6_ADDR_GLOBAL: 4,
        IPV6_ADDR_SITELOCAL: 3,
        IPV6_ADDR_LINKLOCAL: 2,
        IPV6_ADDR_LOOPBACK: 1,
    }
    sa = in6_getscope(a)
    if sa == -1:
        sa = IPV6_ADDR_LOOPBACK
    sb = in6_getscope(b)
    if sb == -1:
        sb = IPV6_ADDR_LOOPBACK
    wa = weights.get(sa, 1)
    wb = weights.get(sb, 1)
    if wa == wb:
        return 0
    return 1 if wa > wb else -1


def in6_get_common_plen(a, b) -> int:
    ba = socket.inet_pton(socket.AF_INET6, a)
    bb = socket.inet_pton(socket.AF_INET6, b)

    def matching_bits(byte1: int, byte2: int) -> int:
        for i in range(8):
            mask = 0x80 >> i
            if (byte1 & mask) != (byte2 & mask):
                return i
        return 8

    for i in range(16):
        mb = matching_bits(ba[i], bb[i])
        if mb != 8:
            return 8 * i + mb
    return 128


def in6_isvalid(address) -> bool:
    try:
        socket.inet_pton(socket.AF_INET6, address)
        return True
    except Exception:
        return False


def in6_isaddr6to4(x: str) -> bool:
    b = socket.inet_pton(socket.AF_INET6, x)
    return b[:2] == b" \x02"


def in6_isaddrTeredo(x: str) -> bool:
    bx = socket.inet_pton(socket.AF_INET6, x)[:4]
    bp = socket.inet_pton(socket.AF_INET6, conf.teredoPrefix)[:4]
    return bx == bp


def teredoAddrExtractInfo(x: str) -> Tuple[str, int, str, int]:
    addr = socket.inet_pton(socket.AF_INET6, x)
    server = socket.inet_ntop(socket.AF_INET, addr[4:8])
    flag = struct.unpack("!H", addr[8:10])[0]
    port_b = bytes((addr[10] ^ 0xFF, addr[11] ^ 0xFF))
    mappedport = struct.unpack("!H", port_b)[0]
    mapped_b = bytes((addr[12] ^ 0xFF, addr[13] ^ 0xFF, addr[14] ^ 0xFF, addr[15] ^ 0xFF))
    mappedaddr = socket.inet_ntop(socket.AF_INET, mapped_b)
    return server, flag, mappedaddr, mappedport


def in6_iseui64(x: str) -> bool:
    s = socket.inet_pton(socket.AF_INET6, "::ff:fe00:0")
    bx = socket.inet_pton(socket.AF_INET6, x)
    return in6_and(bx, s) == s


def in6_isanycast(x: str) -> bool:
    if in6_iseui64(x):
        s = "::fdff:ffff:ffff:ff80"
        bx = socket.inet_pton(socket.AF_INET6, x)
        bs = socket.inet_pton(socket.AF_INET6, s)
        return in6_and(bx, bs) == bs
    warnings.warn("in6_isanycast(): TODO not EUI-64")
    return False


def in6_getnsma(a: bytes) -> bytes:
    r = in6_and(a, socket.inet_pton(socket.AF_INET6, "::ff:ffff"))
    r = in6_or(socket.inet_pton(socket.AF_INET6, "ff02::1:ff00:0"), r)
    return r


def in6_getnsmac(a: bytes) -> str:
    d = struct.unpack("16B", a)
    last4 = d[-4:]
    return "33:33:" + ":".join("%.2x" % x for x in last4)


def in6_getha(prefix: str) -> str:
    bp = socket.inet_pton(socket.AF_INET6, prefix)
    net = in6_and(bp, in6_cidr2mask(64))
    res = in6_or(net, socket.inet_pton(socket.AF_INET6, "::fdff:ffff:ffff:fffe"))
    return socket.inet_ntop(socket.AF_INET6, res)


def in6_getAddrType(addr: str) -> int:
    naddr = socket.inet_pton(socket.AF_INET6, addr)
    paddr = socket.inet_ntop(socket.AF_INET6, naddr)
    addrType = 0
    if (naddr[0] & 0xE0) == 0x20:
        addrType = IPV6_ADDR_UNICAST | IPV6_ADDR_GLOBAL
        if naddr[0] == 0x20 and naddr[1] == 0x02:
            addrType |= IPV6_ADDR_6TO4
    elif naddr[0] == 0xFF:
        # scope nibble from normalized printable string
        try:
            sn = paddr[3]
        except Exception:
            sn = "e"
        if sn == "2":
            addrType = IPV6_ADDR_LINKLOCAL | IPV6_ADDR_MULTICAST
        elif sn in ("e", "E"):
            addrType = IPV6_ADDR_GLOBAL | IPV6_ADDR_MULTICAST
        else:
            addrType = IPV6_ADDR_GLOBAL | IPV6_ADDR_MULTICAST
    elif naddr[0] == 0xFE and (int(paddr[2], 16) & 0xC) == 0x8:
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
    res = first_b + m[2:4] + ":" + m[4:6] + "FF:FE" + m[6:8] + ":" + m[8:12]
    return res.upper()


def in6_ifaceidtomac(ifaceid_s: str) -> Optional[str]:
    try:
        ifaceid = socket.inet_pton(socket.AF_INET6, "::" + ifaceid_s)[8:16]
    except Exception:
        return None
    if ifaceid[3:5] != b"\xff\xfe":
        return None
    first = struct.unpack("B", ifaceid[:1])[0]
    ulbit = 2 * [1, "-", 0][first & 0x02]
    first_b = struct.pack("B", ((first & 0xFD) | ulbit))
    oui = first_b + ifaceid[1:3]
    end = ifaceid[5:]
    return ":".join("%.02x" % x for x in (oui + end))


def in6_addrtomac(addr: str) -> Optional[str]:
    mask = socket.inet_pton(socket.AF_INET6, "::ffff:ffff:ffff:ffff")
    baddr = socket.inet_pton(socket.AF_INET6, addr)
    x = in6_and(mask, baddr)
    ifaceid = socket.inet_ntop(socket.AF_INET6, x)[2:]
    return in6_ifaceidtomac(ifaceid)


def in6_addrtovendor(addr: str) -> Optional[str]:
    mac = in6_addrtomac(addr)
    if mac is None:
        return None
    if not getattr(conf, "manufdb", None):
        return None
    res = conf.manufdb._get_manuf(mac)  # type: ignore[attr-defined]
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
        baddr = socket.inet_pton(socket.AF_INET6, addr)
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
        b_grpid = struct.pack("!I", i_grpid)
    a = (
        b"\xff"
        + struct.pack("B", ((0x3 << 4) | scope) & 0xFF)
        + b"\x00"
        + b"\xff"
        + iid
        + b_grpid
    )
    return socket.inet_ntop(socket.AF_INET6, a)


def in6_get6to4Prefix(addr: str) -> Optional[str]:
    try:
        b4 = socket.inet_pton(socket.AF_INET, addr)
    except Exception:
        return None
    b6 = b"\x20\x02" + b4 + b"\x00" * 10
    return socket.inet_ntop(socket.AF_INET6, b6)


def in6_6to4ExtractAddr(addr: str) -> Optional[str]:
    try:
        baddr = socket.inet_pton(socket.AF_INET6, addr)
    except Exception:
        return None
    if baddr[:2] != b" \x02":
        return None
    return socket.inet_ntop(socket.AF_INET, baddr[2:6])


def in6_getLocalUniquePrefix() -> str:
    tod = time.time()
    i = int(tod)
    j = int((tod - i) * (2**32))
    btod = struct.pack("!II", i, j)
    mac = RandMAC()
    eui64_s = in6_mactoifaceid(str(mac))
    eui64_b = socket.inet_pton(socket.AF_INET6, "::" + eui64_s)[8:16]
    digest = hashlib.sha1(btod + eui64_b).digest()
    gid = digest[:5]
    a = b"\xfd" + gid + b"\x00" * 10
    return socket.inet_ntop(socket.AF_INET6, a)


def in6_getRandomizedIfaceId(ifaceid: str, previous: Optional[str] = None) -> Tuple[str, str]:
    if previous is None:
        b_previous = bytes(RandBin(8))
    else:
        b_previous = socket.inet_pton(socket.AF_INET6, "::" + previous)[8:16]
    b_ifaceid = socket.inet_pton(socket.AF_INET6, "::" + ifaceid)[8:16]
    digest = hashlib.md5(b_ifaceid + b_previous).digest()
    s1 = bytearray(digest[0:8])
    s2 = digest[8:16]
    s1[0] = s1[0] & (~0x04 & 0xFF)
    p1 = socket.inet_ntop(socket.AF_INET6, b"\xff" * 8 + bytes(s1))[20:]
    p2 = socket.inet_ntop(socket.AF_INET6, b"\xff" * 8 + s2)[20:]
    return p1, p2


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
    b = b"".join(res)
    return socket.inet_ntop(socket.AF_INET6, b)


def in6_ptoc(addr: str) -> Optional[str]:
    try:
        d = struct.unpack("!IIII", socket.inet_pton(socket.AF_INET6, addr))
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
    def _cmp(x: str, y: str) -> int:
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

    cand_iter: Iterator[Tuple[str, int, str]]
    if in6_isgladdr(addr) or in6_isuladdr(addr):
        cand_iter = (x for x in laddr if x[1] == IPV6_ADDR_GLOBAL)
    elif in6_islladdr(addr):
        cand_iter = (x for x in laddr if x[1] == IPV6_ADDR_LINKLOCAL)
    elif in6_issladdr(addr):
        cand_iter = (x for x in laddr if x[1] == IPV6_ADDR_SITELOCAL)
    elif in6_ismaddr(addr):
        if in6_ismnladdr(addr):
            cand_iter = iter([("::1", 16, conf.loopback_name)])
        elif in6_ismgladdr(addr):
            cand_iter = (x for x in laddr if x[1] == IPV6_ADDR_GLOBAL)
        elif in6_ismlladdr(addr):
            cand_iter = (x for x in laddr if x[1] == IPV6_ADDR_LINKLOCAL)
        elif in6_ismsladdr(addr):
            cand_iter = (x for x in laddr if x[1] == IPV6_ADDR_SITELOCAL)
        else:
            cand_iter = iter([])
    elif addr == "::" and plen == 0:
        cand_iter = (x for x in laddr if x[1] == IPV6_ADDR_GLOBAL)
    elif addr == "::1":
        cand_iter = (x for x in laddr if x[1] == IPV6_ADDR_LOOPBACK)
    else:
        cand_iter = iter([])

    res = [x[0] for x in cand_iter]
    res.sort(key=functools.cmp_to_key(_cmp))
    return res


def get_source_addr_from_candidate_set(dst: str, candidate_set: List[str]) -> str:
    if not candidate_set:
        return ""

    dst_ip = int.from_bytes(socket.inet_pton(socket.AF_INET6, dst), "big")

    def scope(addr_s: str) -> str:
        b = socket.inet_pton(socket.AF_INET6, addr_s)
        if addr_s == "::1":
            return "node"
        if (b[0] == 0xFE) and ((b[1] & 0xC0) == 0x80):
            return "link"
        if (b[0] & 0xFE) == 0xFC:
            return "unique_local"
        if b[0] == 0xFF:
            if b[1] == 0x02:
                return "multicast_link"
            if b[1] == 0x0E:
                return "multicast_global"
            return "multicast_other"
        return "global"

    dst_scope = scope(dst)

    def is_scope_appropriate(src_scope: str, dst_scope_: str) -> bool:
        if src_scope == "unknown":
            return False
        if dst_scope_ == "node":
            return src_scope == "node"
        if dst_scope_ in ("link", "multicast_link"):
            return src_scope == "link"
        if dst_scope_ == "unique_local":
            return src_scope in ("unique_local", "global")
        if dst_scope_ in ("global", "multicast_global"):
            return src_scope == "global"
        if dst_scope_ == "multicast_other":
            return src_scope == "global"
        if dst_scope_ == "unknown":
            return False
        return False

    def common_plen_int(a_int: int, b_int: int) -> int:
        x = a_int ^ b_int
        if x == 0:
            return 128
        return 128 - x.bit_length()

    def cmp(a: str, b: str) -> int:
        a_ip = int.from_bytes(socket.inet_pton(socket.AF_INET6, a), "big")
        b_ip = int.from_bytes(socket.inet_pton(socket.AF_INET6, b), "big")

        a_eq = a_ip == dst_ip
        b_eq = b_ip == dst_ip
        if a_eq and not b_eq:
            return 1
        if not a_eq and b_eq:
            return -1
        if a_eq and b_eq:
            return 0

        a_ok = is_scope_appropriate(scope(a), dst_scope)
        b_ok = is_scope_appropriate(scope(b), dst_scope)
        if a_ok and not b_ok:
            return 1
        if not a_ok and b_ok:
            return -1

        pa = common_plen_int(a_ip, dst_ip)
        pb = common_plen_int(b_ip, dst_ip)
        if pa > pb:
            return 1
        if pb > pa:
            return -1
        return 0

    candidate_set.sort(key=functools.cmp_to_key(cmp), reverse=True)
    return candidate_set[0]


def rfc3484_cmp(source_a: str, source_b: str) -> int:
    dst = getattr(rfc3484_cmp, "dst", None)
    if dst is None:
        raise NameError("dst")
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


class Net6(Net):
    name = "Net6"
    family = socket.AF_INET6
    max_mask = 128

    @classmethod
    def ip2int(cls, addr):
        a = cls.name2addr(addr)
        packed = socket.inet_pton(socket.AF_INET6, a)
        val1, val2 = struct.unpack("!QQ", packed)
        return (val1 << 64) + val2

    @staticmethod
    def int2ip(val):
        high = val >> 64
        low = val & 0xFFFFFFFFFFFFFFFF
        packed = struct.pack("!QQ", high, low)
        return socket.inet_ntop(socket.AF_INET6, packed)
