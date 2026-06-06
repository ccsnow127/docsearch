# utils6 Baseline Documentation

## Module: utils6

**purpose** This module provides IPv6-focused utilities used by Scapy for address classification, normalization, bitwise/prefix operations, and generation/extraction of IPv6-derived identifiers (EUI-64, solicited-node multicast, 6to4, Teredo, RFC 1924 compact form). It also implements a constrained RFC 3484-style source-address selection workflow by building a scope-appropriate candidate set for a destination prefix and then choosing the best source based on scope and longest-prefix match.

**main class**
- **Net6** Extends **scapy.base_classes.Net** to represent IPv6 networks (up to /128), providing **ip2int**/**int2ip** conversions between printable IPv6 strings (via **inet_pton/inet_ntop**) and 128-bit integers for network arithmetic and iteration.

**source selection helpers**
- **construct_source_candidate_set** Filters an interface’s assigned addresses (tuples including an address-type constant such as **IPV6_ADDR_GLOBAL/LINKLOCAL/SITELOCAL/LOOPBACK**) into a candidate list matching the destination’s scope, then sorts candidates to prefer global over non-global and native global over 6to4.
- **get_source_addr_from_candidate_set** Chooses the best source for a destination from the candidate list using internal comparators (**scope_cmp**, **rfc3484_cmp**) that apply “same address”, “appropriate scope”, and “longest prefix match” rules.

**address typing, encoding, and transformations**
- **in6_getAddrType** Classifies an IPv6 address into Scapy’s IPv6 type flags (e.g., unicast/multicast, global/link-local, 6to4, loopback, unspecified) using normalized packed/printable forms.
- **in6_mactoifaceid**, **in6_ifaceidtomac**, **in6_addrtomac**, **in6_addrtovendor** Convert between MAC addresses, modified EUI-64 interface identifiers, and IPv6 addresses embedding those identifiers; vendor lookup uses **conf.manufdb** when available.
- **in6_getLinkScopedMcastAddr** Builds RFC 4489 link-scoped multicast addresses from a link-local unicast address IID plus an optional group ID and validated scope.
- **in6_get6to4Prefix**, **in6_6to4ExtractAddr**, **in6_isaddr6to4** Generate/extract/test 6to4 addressing (2002::/16) and embedded IPv4.
- **in6_isaddrTeredo**, **teredoAddrExtractInfo** Detect Teredo addresses under **conf.teredoPrefix** and extract server/flags/mapped endpoint information.
- **in6_getLocalUniquePrefix**, **in6_getRandomizedIfaceId** Generate RFC 4193-like ULA prefixes and RFC 3041 temporary interface identifiers (returning both the new IID and the history value).
- **in6_ctop**, **in6_ptoc** Convert between printable IPv6 and RFC 1924 “base85” compact representation.

**bitwise, prefix, and membership utilities**
- **in6_or**, **in6_and**, **in6_xor** Perform bitwise operations on packed (network-format) IPv6 addresses using Scapy’s bytewise helpers.
- **in6_cidr2mask**, **in6_mask2cidr** Convert between prefix length and 128-bit packed masks.
- **in6_getnsma**, **in6_getnsmac** Compute solicited-node multicast IPv6 addresses (packed) and their corresponding multicast MAC addresses.
- **in6_getha** Computes the “all home agents” anycast address for a /64 prefix.
- **in6_ptop** Normalizes printable IPv6 strings via pack/unpack round-tripping.
- **in6_isincluded** Tests whether an address is within a prefix/length; many predicates (**in6_islladdr**, **in6_isgladdr**, **in6_isuladdr**, multicast scope checks, documentation prefix checks, etc.) are thin wrappers over this.
- **in6_getscope** Maps an address to a scope constant used by source selection and candidate filtering.
- **in6_get_common_plen** (with internal **matching_bits**) computes the common-prefix length between two IPv6 addresses for longest-prefix matching.
- **in6_iseui64**, **in6_isanycast**, **in6_isvalid** Detect EUI-64-derived IIDs, a limited anycast pattern (EUI-64 case), and validate IPv6 address strings.

---

## Class: Net6

**Interface:**
```python
class Net6(Net):

    name = "Net6"  # type: str
    family = socket.AF_INET6  # type: int
    max_mask = 128  # type: int

    def ip2int(cls, addr)
    def int2ip(val)
```

### Method: Net6.ip2int

**Net6.ip2int**: Convert an IPv6 address (or hostname resolvable to IPv6) into a single 128-bit Python integer.
**Signature**: @classmethod def ip2int(cls, addr: str) -> int
**Parameters**:
- addr (str): IPv6 address string or hostname; is first normalized/resolved to an IPv6 address via cls.name2addr(addr) before conversion.
**Behavior**:
- Resolve/normalize the input by calling cls.name2addr(addr), producing an IPv6 address string suitable for binary conversion.
- Convert that IPv6 string to its 16-byte network-order (big-endian) packed form using inet_pton(AF_INET6, ...).
- Interpret the 16 bytes as two unsigned 64-bit big-endian integers by unpacking with struct.unpack('!QQ', packed_bytes), yielding (val1, val2).
- Combine the two halves into a single integer representing the full 128-bit address: (val1 << 64) + val2.
- No explicit error handling is performed in this method; any exception raised by name resolution, inet_pton, or struct.unpack propagates to the caller.
**Returns**:
- An int in the range 0..(2**128 - 1) representing the IPv6 address, where the first 8 bytes are the high 64 bits and the last 8 bytes are the low 64 bits.
**Notes**:
- Endianness is network byte order (big-endian) due to the '!QQ' format.
- The method depends on Net.name2addr (inherited) for hostname/address normalization; its behavior affects what inputs are accepted.

### Method: Net6.int2ip

**Net6.int2ip**: Convert a 128-bit integer into its canonical printable IPv6 address string.
**Signature**: @staticmethod def int2ip(val: int) -> str
**Parameters**:
- val (int): Integer to convert; treated as an unsigned 128-bit value by splitting into high/low 64-bit parts.
**Behavior**:
- Compute the high 64 bits as val >> 64.
- Compute the low 64 bits as val & 0xffffffffffffffff.
- Pack these two unsigned 64-bit values into a 16-byte network-order (big-endian) buffer using struct.pack('!QQ', high, low).
- Convert the packed 16-byte IPv6 address to printable form using inet_ntop(AF_INET6, packed_bytes) and return it.
- No explicit range checking is performed; any exception from struct.pack or inet_ntop propagates to the caller.
**Returns**:
- A str containing the printable IPv6 representation corresponding to the packed 16-byte value derived from val.

---

## Function: construct_source_candidate_set

```python
def construct_source_candidate_set(addr, plen, laddr)
```

**construct_source_candidate_set**: Build and return a sorted list of candidate IPv6 source addresses from an interface address list that match the scope implied by a given destination prefix.
**Signature**: def construct_source_candidate_set(addr: str, plen: int, laddr: Iterator[Tuple[str, int, str]]) -> List[str]
**Parameters**:
- addr (str): IPv6 address in printable form representing the route/prefix base whose scope determines which local addresses are eligible.
- plen (int): Prefix length associated with addr; only used for special-case handling of the default route (::/0).
- laddr (Iterator[Tuple[str, int, str]]): Iterable of interface address tuples; each tuple is (address_str, addr_type_int, iface_name_str). Only address_str and addr_type_int are used.
**Behavior**:
- Define an internal comparator used only for sorting the resulting address strings:
- For each compared address x and y, compute flags x_global and y_global as 1 if the address is a global unicast address (in6_isgladdr), else 0.
- Compute res = y_global - x_global.
- If res != 0 (i.e., one is global and the other is not), return res so that global addresses sort before non-global when used with cmp_to_key.
- If y_global != 1 (meaning both are non-global), return res (which will be 0), leaving their relative order unchanged by the comparator.
- If both are global (y_global == 1 and res == 0), prefer “native” global over 6to4:
- If x is not a 6to4 address (not in6_isaddr6to4(x)), return -1 (x should come before y).
- Otherwise return -res (which is 0), meaning no further ordering is imposed in this branch.
- Select a generator over laddr (or a synthetic singleton list) to form the candidate set based on the scope/type of addr:
- If addr is global unicast (in6_isgladdr) or unique-local (in6_isuladdr): include only entries from laddr whose type field equals IPV6_ADDR_GLOBAL.
- Else if addr is link-local unicast (in6_islladdr): include only entries whose type equals IPV6_ADDR_LINKLOCAL.
- Else if addr is site-local unicast (in6_issladdr): include only entries whose type equals IPV6_ADDR_SITELOCAL.
- Else if addr is multicast (in6_ismaddr):
- If node-local multicast (in6_ismnladdr): candidate set is exactly one tuple ('::1', 16, conf.loopback_name) (then only its address string is used).
- Else if global multicast (in6_ismgladdr): include only entries whose type equals IPV6_ADDR_GLOBAL.
- Else if link-local multicast (in6_ismlladdr): include only entries whose type equals IPV6_ADDR_LINKLOCAL.
- Else if site-local multicast (in6_ismsladdr): include only entries whose type equals IPV6_ADDR_SITELOCAL.
- Otherwise: leave candidate set empty.
- Else if addr == '::' and plen == 0 (default route): include only entries whose type equals IPV6_ADDR_GLOBAL.
- Else if addr == '::1': include only entries whose type equals IPV6_ADDR_LOOPBACK.
- Else: leave candidate set empty.
- Convert the chosen candidate-set iterator into a list of address strings by taking element 0 of each tuple.
- Sort that list in-place using the internal comparator via functools.cmp_to_key, with the intent that global addresses appear first (and among globals, non-6to4 may be preferred).
- Return the sorted list.
**Returns**:
- List[str]: The sorted list of candidate source address strings; may be empty if no rule matched or no addresses of the required type exist.
**Notes**:
- The function relies on laddr tuples using Scapy’s IPv6 address type constants in the second element.
- The internal comparator is local to this function; the module-level name `cset_sort` is a different entity.

---

## Function: cset_sort

```python
def cset_sort(x, y)
```

**cset_sort**: Compare two IPv6 address strings for ordering within a candidate set, prioritizing global addresses and (among globals) preferring native over 6to4.
**Signature**: def cset_sort(x: str, y: str) -> int
**Parameters**:
- x (str): First IPv6 address in printable form.
- y (str): Second IPv6 address in printable form.
**Behavior**:
- Determine whether each address is global unicast:
- Set x_global to 1 if in6_isgladdr(x) is True, else 0.
- Set y_global to 1 if in6_isgladdr(y) is True, else 0.
- Compute res = y_global - x_global.
- If res != 0, return res so that when used as a comparator, global addresses are ordered before non-global addresses.
- If res == 0 and y_global != 1 (i.e., both are non-global), return res (0), indicating equality/no preference.
- If both are global (res == 0 and y_global == 1):
- If x is not a 6to4 address (not in6_isaddr6to4(x)), return -1 to prefer x over y.
- Otherwise return -res (which is 0), indicating no further preference.
**Returns**:
- int: A comparator-style result intended for use with cmp_to_key: negative means x should come before y, positive means after, zero means no preference.
**Notes**:
- This comparator does not fully order all inputs (it can return 0 for distinct addresses), so sorting stability may affect final ordering.
- This is the module-level function; `construct_source_candidate_set` also defines a similarly named local comparator with the same logic.

---

## Function: get_source_addr_from_candidate_set

```python
def get_source_addr_from_candidate_set(dst, candidate_set)
```

**get_source_addr_from_candidate_set**: Select the best IPv6 source address for a given destination from a provided candidate set using a limited, deterministic RFC 3484-like comparison (same-address, scope reachability, then longest common prefix).

**Signature**: def get_source_addr_from_candidate_set(dst: str, candidate_set: List[str]) -> str

**Parameters**:
- dst (str): Destination IPv6 address in printable form.
- candidate_set (List[str]): List of candidate source IPv6 addresses (printable form) to be ranked; this list is sorted in-place.

**Behavior**:
- Input expectations:
  - `dst` and every element of `candidate_set` MUST be parseable as IPv6 addresses.
  - `candidate_set` may contain duplicates; sorting MUST remain deterministic and MUST NOT error.
  - Address comparisons MUST be performed on parsed IPv6 address values (not raw strings) unless the implementation first canonicalizes all addresses into a consistent normalized string form; equality and prefix computations MUST reflect actual IPv6 address value equality.
- Empty input handling:
  - If `candidate_set` is empty, return the empty string `""` (exceptional/should-not-happen case).
- High-level algorithm:
  - Rank candidates by sorting `candidate_set` in-place using a comparator that compares two candidates `a` and `b` relative to the fixed destination `dst`.
  - Use `functools.cmp_to_key` to adapt the comparator for sorting.
  - Sort with `reverse=True` so that “better” candidates (those that outrank others under the comparator) end up earlier in the list.
  - After sorting completes, return the first element of the now-sorted `candidate_set`.
- Comparator definition and sign semantics (MUST be unambiguous and consistent):
  - The comparator is a pure function of `(a, b, dst)` and returns:
    - `+1` if `a` strictly outranks `b` (meaning `a` is the better source address for `dst`).
    - `-1` if `b` strictly outranks `a`.
    - `0` if `a` and `b` tie under all implemented rules.
  - The comparator MUST NOT depend on mutable global state or mutable function attributes. The destination used for comparison is exactly the `dst` argument passed into `get_source_addr_from_candidate_set`, and it is fixed for the entire sort.
  - The comparator MUST be antisymmetric and self-consistent:
    - For all `a, b`: `cmp(a, b, dst) == -cmp(b, a, dst)`.
    - For all `a`: `cmp(a, a, dst) == 0`.
  - The comparator MUST be transitive with respect to the induced ordering so that sorting is deterministic and does not produce inconsistent results.
  - There MUST be exactly one authoritative comparator used for sorting inside this function; do not implement or retain alternate/competing comparator implementations that could disagree or be stateful.
- Comparator rule order (applied in order; the first rule that decides determines the result):
  - Same-address preference (highest priority; MUST be implemented exactly and consistently):
    - Prefer a candidate whose IPv6 address value is exactly equal to `dst`.
    - Decision table (must be implemented exactly):
      - If `a == dst` and `b != dst`: return `+1`.
      - If `a != dst` and `b == dst`: return `-1`.
      - If `a == dst` and `b == dst`: return `0`.
      - If `a != dst` and `b != dst`: no decision from this rule; proceed to next rule.
  - Scope reachability / appropriateness (second priority; MUST be an explicit reachability predicate, not a generic numeric “scope weight” comparison):
    - Define a deterministic scope classification function `scope(addr)` that maps an IPv6 address to exactly one of the following scope classes:
      - `node`: loopback (`::1`).
      - `link`: link-local unicast (`fe80::/10`).
      - `unique_local`: unique local unicast (ULA) (`fc00::/7`).
      - `global`: all other unicast addresses not covered above, including IPv4-mapped/translated forms if they parse as IPv6 and are not in the above ranges.
      - `multicast_link`: multicast with link-local scope (`ff02::/16`).
      - `multicast_global`: multicast with global scope (`ff0e::/16`).
      - `multicast_other`: any other multicast (`ff00::/8`) scope not covered above (treat as neither link-local nor global for reachability decisions below).
      - `unknown`: any address that does not fit the above categories (should be rare if parsing succeeds; included to make behavior total and deterministic).
    - Define a deterministic reachability predicate `is_scope_appropriate(src_scope, dst_scope)` that returns True iff a source of `src_scope` is considered able/appropriate to reach a destination of `dst_scope` under this function’s limited model:
      - If `dst_scope` is `node`: only `src_scope == node` is appropriate.
      - If `dst_scope` is `link` or `multicast_link`: `src_scope` is appropriate iff `src_scope` is `link` (and NOT `global`, `unique_local`, or `node`).
      - If `dst_scope` is `unique_local`: `src_scope` is appropriate iff `src_scope` is `unique_local` or `global`.
      - If `dst_scope` is `global` or `multicast_global`: `src_scope` is appropriate iff `src_scope` is `global`.
      - If `dst_scope` is `multicast_other`: treat as `global` for appropriateness (i.e., only `src_scope == global` is appropriate) unless it is explicitly `multicast_link` or `multicast_global` as classified above.
      - If `dst_scope` is `unknown`: no source is considered scope-appropriate (i.e., `is_scope_appropriate` is False for all `src_scope`), so this rule will not prefer either candidate; comparison proceeds to the next rule.
      - If `src_scope` is `unknown`: it is never considered appropriate for any destination scope.
    - Scope rule decision:
      - Let `a_ok = is_scope_appropriate(scope(a), scope(dst))` and `b_ok = is_scope_appropriate(scope(b), scope(dst))`.
      - If `a_ok` is True and `b_ok` is False: return `+1`.
      - If `a_ok` is False and `b_ok` is True: return `-1`.
      - If both are equal (both True or both False): no decision from this rule; proceed to next rule.
    - Notes/invariants:
      - This rule is strictly about appropriateness (a boolean reachability model), not about “which scope is larger” or “>=” comparisons.
      - If both candidates are appropriate, this rule MUST NOT introduce any further ordering between them; only later rules may decide.
  - Longest common prefix length (third priority):
    - Prefer the candidate with the longer common prefix with `dst`, measured as the number of leading equal bits in the 128-bit IPv6 addresses.
    - The prefix length MUST be computed on the 128-bit integer representation of the parsed IPv6 addresses.
    - If `a` has a strictly longer matching prefix length than `b`, return `+1`; if strictly shorter, return `-1`.
    - If prefix lengths are equal, return `0` (tie across all implemented rules).
- Determinism and side effects:
  - The only intended side effect is that `candidate_set` is mutated by being sorted in-place.
  - The ranking MUST be deterministic for a given `(dst, candidate_set)`; it MUST NOT depend on sort timing, iteration order, hash randomization, or mutable shared state.
  - If the comparator returns `0` for two distinct candidates (true tie under all rules), their relative order after sorting is determined by Python’s stable sort and the existing order in `candidate_set`; this is acceptable and still deterministic given a fixed input list order.
- Ranking examples (illustrative relationships; not tied to any specific test vectors):
  - If one candidate equals `dst` and another does not, the one equal to `dst` must appear before the other regardless of scope or prefix considerations.
  - If neither candidate equals `dst`, and exactly one candidate is scope-appropriate for `dst` under `is_scope_appropriate`, the scope-appropriate candidate must appear before the scope-inappropriate one regardless of prefix length.
  - If both candidates are equally scope-appropriate (both appropriate or both inappropriate) and neither equals `dst`, the candidate with the longer common prefix with `dst` must appear before the one with the shorter common prefix.

**Returns**:
- str: The selected best source address (the first element after in-place sorting); `""` if `candidate_set` was empty.

---

## Function: scope_cmp

```python
def scope_cmp(a, b)
```

**scope_cmp**: Compare two IPv6 addresses by their scope ranking (global > site-local > link-local > loopback) for use in source-address selection.
**Signature**: def scope_cmp(a: str, b: str) -> int
**Parameters**:
- a (str): IPv6 address in printable form.
- b (str): IPv6 address in printable form.
**Behavior**:
- Map Scapy scope constants to an ordering weight:
- IPV6_ADDR_GLOBAL -> 4
- IPV6_ADDR_SITELOCAL -> 3
- IPV6_ADDR_LINKLOCAL -> 2
- IPV6_ADDR_LOOPBACK -> 1
- Determine each address scope using in6_getscope:
- sa = in6_getscope(a); if sa == -1, treat it as IPV6_ADDR_LOOPBACK.
- sb = in6_getscope(b); if sb == -1, treat it as IPV6_ADDR_LOOPBACK.
- Convert sa and sb to their weights using the mapping.
- Compare weights:
- If equal, return 0.
- If sa weight > sb weight, return 1.
- Otherwise return -1.
**Returns**:
- int: 1 if a has broader/higher-ranked scope than b, -1 if narrower/lower-ranked, 0 if equal after normalization.
**Notes**:
- Unknown scopes (-1) are coerced to loopback for comparison purposes.

---

## Function: rfc3484_cmp

```python
def rfc3484_cmp(source_a, source_b)
```

**rfc3484_cmp**: Compare two candidate IPv6 source addresses for a fixed destination using a limited subset of RFC 3484 source address selection rules.
**Signature**: def rfc3484_cmp(source_a: str, source_b: str) -> int
**Parameters**:
- source_a (str): First candidate source IPv6 address in printable form.
- source_b (str): Second candidate source IPv6 address in printable form.
**Behavior**:
- Apply the following rules in order; return as soon as a rule decides:
- Rule 1 (Prefer same address):
- If source_a equals the destination address (dst in the original calling context), return 1.
- If source_b equals the destination address, return 1.
- (Note: both branches return 1; no branch returns -1 here.)
- Rule 2 (Prefer appropriate scope):
- Compute tmp = scope_cmp(source_a, source_b).
- If tmp == -1 (source_a has narrower scope than source_b):
- If scope_cmp(source_a, dst) == -1 (source_a is narrower than destination), return 1; else return -1.
- Else if tmp == 1 (source_a has broader scope than source_b):
- If scope_cmp(source_b, dst) == -1 (source_b is narrower than destination), return 1; else return -1.
- If tmp == 0, continue.
- Rules 3–7 are explicitly not implemented and are skipped.
- Rule 8 (Longest prefix match):
- Compute tmp1 = in6_get_common_plen(source_a, dst).
- Compute tmp2 = in6_get_common_plen(source_b, dst).
- If tmp1 > tmp2, return 1.
- Else if tmp2 > tmp1, return -1.
- Else return 0.
**Returns**:
- int: Comparator-style result where positive indicates preference for source_a over source_b, negative indicates preference for source_b, and 0 indicates no preference.
**Notes**:
- This comparator depends on an external destination value `dst` in the original implementation context; when re-implementing as a standalone function, dst must be provided or captured equivalently.
- Rule 1’s behavior is asymmetric/non-discriminating when either candidate equals dst (it always returns 1), which can affect strict ordering.

---

## Function: in6_getAddrType

```python
def in6_getAddrType(addr)
```

**in6_getAddrType**: Classify an IPv6 address string into Scapy IPv6 address-type bitflags (unicast/multicast and scope, plus 6to4 marker), using Scapy’s canonical constant bit layout.

**Signature**: def in6_getAddrType(addr: str) -> int

**Parameters**:
- addr (str): IPv6 address in printable form; must be parseable by inet_pton(AF_INET6). Any accepted textual IPv6 form (compressed zeros, mixed-case hex) is allowed.

**Behavior**:
- Convert addr to 16-byte network form using inet_pton(AF_INET6, addr); name the result naddr (type: bytes, length 16).
- Normalize it back to printable canonical form using inet_ntop(AF_INET6, naddr); name the result paddr (type: str).
- Initialize addrType = 0.
- Constants / bit layout requirements (critical):
  - The returned value is a bitmask composed of Scapy’s IPv6 address-type constants.
  - Implementations must use the exact numeric values from Scapy for the following constants:
    - IPV6_ADDR_UNICAST
    - IPV6_ADDR_MULTICAST
    - IPV6_ADDR_GLOBAL
    - IPV6_ADDR_LINKLOCAL
    - IPV6_ADDR_LOOPBACK
    - IPV6_ADDR_UNSPECIFIED
    - IPV6_ADDR_6TO4
  - Do not invent substitute/stub values for these constants. If Scapy is not available at runtime, the implementation must still provide the same numeric mapping as Scapy (e.g., by importing from Scapy when present, otherwise defining the constants to the exact Scapy values). The classification logic is validated by callers/tests using bitwise checks against those specific bits.
  - Invariant: For any returned addrType, each property (e.g., “is global”) must be independently testable via bitwise-AND with the corresponding Scapy constant, and combinations must be formed only by bitwise-OR of those constants.
- Determine type by inspecting naddr and/or paddr in the following order (first matching branch wins):
  - Global unicast 2000::/3:
    - If (naddr[0] & 0xE0) == 0x20:
      - Set addrType = IPV6_ADDR_UNICAST | IPV6_ADDR_GLOBAL.
      - Additionally, detect 6to4 (2002::/16):
        - If naddr[0] == 0x20 and naddr[1] == 0x02, then set addrType |= IPV6_ADDR_6TO4.
  - Multicast ff00::/8:
    - Else if naddr[0] == 0xFF:
      - Determine multicast scope from the low nibble of the second byte.
      - This implementation derives the scope nibble by indexing the normalized printable string:
        - Use paddr[3] (the 4th character) as the scope nibble character for normalized strings beginning with "ff" followed by two hex digits (e.g., "ff0e::...").
        - Interpret paddr[3] as a hexadecimal nibble (case-insensitive).
      - Scope classification:
        - If paddr[3] is '2' (link-local scope), set addrType = IPV6_ADDR_LINKLOCAL | IPV6_ADDR_MULTICAST.
        - Else if paddr[3] is 'e' or 'E' (global scope), set addrType = IPV6_ADDR_GLOBAL | IPV6_ADDR_MULTICAST.
        - Else: default to addrType = IPV6_ADDR_GLOBAL | IPV6_ADDR_MULTICAST.
  - Link-local unicast fe80::/10:
    - Else if naddr[0] == 0xFE and (int(paddr[2], 16) & 0xC) == 0x8:
      - Set addrType = IPV6_ADDR_UNICAST | IPV6_ADDR_LINKLOCAL.
    - Note: This link-local check intentionally uses paddr[2] (third character of the normalized string) as a proxy for the relevant bits, rather than directly masking naddr[1]. Implementations must preserve this behavior.
  - Loopback:
    - Else if paddr == "::1":
      - Set addrType = IPV6_ADDR_LOOPBACK.
  - Unspecified:
    - Else if paddr == "::":
      - Set addrType = IPV6_ADDR_UNSPECIFIED.
  - Default:
    - Else:
      - Treat everything else as global unicast (including deprecated site-local ranges) by setting addrType = IPV6_ADDR_GLOBAL | IPV6_ADDR_UNICAST.
- Return addrType.

**Returns**:
- int: Bitmask composed from Scapy constants IPV6_ADDR_UNICAST, IPV6_ADDR_MULTICAST, IPV6_ADDR_GLOBAL, IPV6_ADDR_LINKLOCAL, IPV6_ADDR_LOOPBACK, IPV6_ADDR_UNSPECIFIED, and optionally IPV6_ADDR_6TO4. The numeric values of these constants must match Scapy’s canonical definitions so that bitwise tests against each constant behave identically to Scapy.

---

## Function: in6_mactoifaceid

```python
def in6_mactoifaceid(mac, ulbit=None)
```

**in6_mactoifaceid**: Convert a 48-bit Ethernet MAC address string into a modified EUI-64 IPv6 interface identifier string, optionally forcing the U/L bit.
**Signature**: def in6_mactoifaceid(mac: str, ulbit: Optional[int] = None) -> str
**Parameters**:
- mac (str): MAC address in colon-separated lowercase/uppercase hex form of length 17 (e.g., "aa:bb:cc:dd:ee:ff").
- ulbit (Optional[int]): If 0 or 1, forces the U/L bit value used in the resulting interface identifier; otherwise (None or invalid), the bit is derived by reversing the MAC’s U/L bit.
**Behavior**:
- Validate formatting:
- If len(mac) != 17, raise ValueError("Invalid MAC").
- Remove colons by splitting on ':' and joining; call the result m.
- If len(m) != 12, raise ValueError("Invalid MAC").
- Parse the first byte: first = int(m[0:2], 16).
- Determine the U/L bit to apply:
- If ulbit is None or ulbit is not exactly 0 or 1:
- Compute ulbit as the reversed value of the MAC’s U/L bit using: ulbit = [1, 0, 0][first & 0x02].
- This yields 1 when the MAC’s bit is 0, and 0 when the MAC’s bit is 1.
- Multiply ulbit by 2 (so it becomes 0x00 or 0x02).
- Compute the modified first byte:
- Clear the MAC’s U/L bit with (first & 0xFD) and OR with ulbit.
- Format as two hex digits: first_b = "%.02x" % (...).
- Construct the modified EUI-64 interface identifier string by inserting "FF:FE" in the middle and grouping as:
- first_b + m[2:4] + ":" + m[4:6] + "FF:FE" + m[6:8] + ":" + m[8:12]
- Uppercase the entire resulting string and return it.
**Returns**:
- str: Modified EUI-64 interface identifier in uppercase, formatted like "XXXX:XXFF:FEXX:XXXX" (with colons as shown).
**Notes**:
- The function enforces only length/colon-removal constraints; it does not validate that each hex pair is valid beyond int() parsing of the first byte.

---

## Function: in6_ifaceidtomac

```python
def in6_ifaceidtomac(ifaceid_s)
```

**in6_ifaceidtomac**: Recover a colon-separated MAC address string from a modified EUI-64 IPv6 interface identifier string; return None if the identifier is not in the expected EUI-64 form.
**Signature**: def in6_ifaceidtomac(ifaceid_s: str) -> Optional[str]
**Parameters**:
- ifaceid_s (str): Interface identifier in printable IPv6 hextet form representing the low 64 bits (e.g., "20b:93ff:feeb:2d3"), possibly compressed; it is parsed by prefixing "::" and using inet_pton(AF_INET6).
**Behavior**:
- Attempt to parse the interface identifier into bytes:
- Build a full IPv6 string by concatenating "::" + ifaceid_s.
- Use inet_pton(AF_INET6, ...) to parse; take only the last 8 bytes ([8:16]) as ifaceid.
- If parsing fails for any reason, return None.
- Verify it matches the modified EUI-64 pattern for a burned-in MAC:
- If ifaceid[3:5] is not exactly b'\xff\xfe', return None.
- Reconstruct the original MAC bytes:
- Extract the first byte as an integer: first = struct.unpack("B", ifaceid[:1])[0].
- Compute ulbit using: ulbit = 2 * [1, '-', 0][first & 0x02].
- This yields 0x02 when the bit is 0, and 0x00 when the bit is 1.
- Replace the U/L bit in the first byte by clearing it and OR-ing ulbit:
- first = struct.pack("B", ((first & 0xFD) | ulbit)).
- Form the OUI part as: oui = first + ifaceid[1:3].
- Form the remaining NIC-specific bytes as: end = ifaceid[5:] (skipping the inserted ff:fe bytes).
- Convert bytes to lowercase hex pairs and join with colons:
- For each byte in (oui + end), format as "%.02x".
- Join the 6 pairs with ':' and return.
**Returns**:
- Optional[str]: The reconstructed MAC address string (six hex pairs separated by ':') if ifaceid_s is parseable and contains the ff:fe marker; otherwise None.
**Notes**:
- The U/L bit handling mirrors the module’s specific logic and may not match all interpretations; it is implemented exactly as described above.
- The returned MAC uses lowercase hex formatting.

---

## Function: in6_addrtomac

```python
def in6_addrtomac(addr)
```

**in6_addrtomac**: Extract a MAC address from an IPv6 address whose interface identifier is in modified EUI-64 form.
**Signature**: def in6_addrtomac(addr: str) -> Optional[str]
**Parameters**:
- addr (str): IPv6 address in printable form.
**Behavior**:
- Build a 128-bit mask corresponding to the low 64 bits set (and high 64 bits cleared) by parsing "::ffff:ffff:ffff:ffff" with inet_pton(AF_INET6).
- Parse addr into 16-byte network form with inet_pton(AF_INET6, addr).
- Compute x = in6_and(mask, parsed_addr), yielding only the low 64 bits of the address.
- Convert x back to printable IPv6 with inet_ntop(AF_INET6, x).
- Remove the leading "::" from that printable form by taking substring [2:], producing ifaceid.
- Return in6_ifaceidtomac(ifaceid).
**Returns**:
- Optional[str]: The extracted MAC address string if addr is parseable and the low 64 bits match the modified EUI-64 ff:fe pattern; otherwise None.
**Notes**:
- Any parsing error from inet_pton(AF_INET6, addr) propagates (it is not caught in this function).
- The slicing [2:] assumes inet_ntop of a low-64-only value begins with "::"; this is relied upon to produce an interface-id string acceptable to in6_ifaceidtomac.

---

## Function: in6_addrtovendor

```python
def in6_addrtovendor(addr)
```

**in6_addrtovendor**: Derive the vendor/manufacturer name from an IPv6 address by extracting its embedded MAC (modified EUI-64) and querying Scapy’s manufacturer database.
**Signature**: def in6_addrtovendor(addr: str) -> Optional[str]
**Parameters**:
- addr (str): IPv6 address in printable form, expected to embed a modified EUI-64 interface identifier.
**Behavior**:
- Call in6_addrtomac(addr) to extract a MAC address.
- If the result is None, return None.
- Check that conf.manufdb is available/truthy.
- If not available, return None.
- Query the manufacturer database using conf.manufdb._get_manuf(mac) and store as res.
- Detect the “unknown vendor” case:
- If len(res) == 17 and res.count(':') != 5, treat res as a MAC-like string returned instead of a vendor name and set res = "UNKNOWN".
- Return res.
**Returns**:
- Optional[str]:
- None if MAC extraction fails or manufacturer DB is unavailable.
- Otherwise the vendor string from the DB, or "UNKNOWN" if the DB indicates no known vendor.
**Notes**:
- This function depends on Scapy’s conf.manufdb implementation and its private method _get_manuf.
- Any exception raised by in6_addrtomac due to invalid IPv6 parsing will propagate (not caught here).

---

## Function: in6_getLinkScopedMcastAddr

```python
def in6_getLinkScopedMcastAddr(addr, grpid=None, scope=2)
```

**in6_getLinkScopedMcastAddr**: Generate an IPv6 multicast address per RFC 4489 using a link-local unicast address to derive the multicast IID and an optional 32-bit group ID.
**Signature**: def in6_getLinkScopedMcastAddr(addr: str, grpid: Optional[Union[bytes, str, int]] = None, scope: int = 2) -> Optional[str]
**Parameters**:
- addr (str): IPv6 address string that must be link-local unicast (must match fe80::/10); used to extract the low 64-bit interface identifier.
- grpid (Optional[Union[bytes, str, int]]): Optional 32-bit group identifier to place in the last 32 bits of the multicast address; accepted forms are 4-byte big-endian bytes, an 8-hex-character string, or an int.
- scope (int): Multicast scope value encoded in the multicast address; must be exactly one of 0, 1, or 2.
**Behavior**:
- Validate scope:
- If scope is not in the set {0, 1, 2}, return None immediately.
- Validate and parse addr:
- If addr is not a link-local IPv6 address (fe80::/10), return None.
- Attempt to parse addr as an IPv6 address using inet_pton(AF_INET6, addr).
- If parsing fails, emit a warning with the exact text "in6_getLinkScopedMcastPrefix(): Invalid address provided" and return None.
- Derive the multicast IID:
- Take the last 8 bytes (low 64 bits) of the parsed IPv6 address; this 8-byte value is the IID used in the multicast address.
- Determine the 32-bit group ID bytes (b_grpid):
- If grpid is None, set b_grpid to four zero bytes.
- Otherwise, interpret grpid as follows:
- If grpid is a str:
- It must have length exactly 8; interpret it as hexadecimal (base 16), then mask with 0xffffffff.
- If length is not 8 or conversion fails, emit a warning with the exact text "in6_getLinkScopedMcastPrefix(): Invalid group id provided" and return None.
- If grpid is bytes:
- It must have length exactly 4; interpret it as an unsigned 32-bit big-endian integer using struct.unpack("!I", grpid).
- If length is not 4 or unpacking fails, emit the same warning text as above and return None.
- If grpid is an int:
- Use it directly as i_grpid (no range enforcement beyond what struct.pack will accept).
- For any other type:
- Emit the same warning text and return None.
- Pack i_grpid into 4 bytes big-endian using struct.pack("!I", i_grpid) to produce b_grpid.
- Construct the multicast address bytes a (16 bytes total) with the following fixed layout:
- Byte 0: 0xff (multicast prefix).
- Byte 1: a combined flags+scope byte computed as ((0x3 << 4) | scope) masked to 8 bits; pack with struct.pack("B", ...).
- Byte 2: 0x00 ("res" field).
- Byte 3: 0xff ("plen" field).
- Bytes 4..11: the 8-byte IID extracted from addr.
- Bytes 12..15: b_grpid (4 bytes).
- Convert the 16-byte result to printable IPv6 form using inet_ntop(AF_INET6, a) and return it.
**Returns**:
- Optional[str]: The generated multicast IPv6 address string on success; None if scope is invalid, addr is not link-local, addr parsing fails, or grpid is invalid.

---

## Function: in6_get6to4Prefix

```python
def in6_get6to4Prefix(addr)
```

**in6_get6to4Prefix**: Build the IPv6 6to4 /48 prefix corresponding to a given IPv4 address.
**Signature**: def in6_get6to4Prefix(addr: str) -> Optional[str]
**Parameters**:
- addr (str): IPv4 address string to embed into a 6to4 prefix.
**Behavior**:
- Attempt to parse addr as an IPv4 address using inet_pton(AF_INET, addr).
- If parsing fails (any exception), return None.
- If parsing succeeds, construct a 16-byte IPv6 address as:
- First 2 bytes: 0x20 0x02 (the 6to4 prefix 2002::/16).
- Next 4 bytes: the parsed IPv4 address bytes.
- Remaining 10 bytes: all zeros.
- Convert the 16-byte IPv6 value to printable form using inet_ntop(AF_INET6, ...) and return it.
**Returns**:
- Optional[str]: Printable IPv6 address representing the 6to4 prefix (with host bits zeroed) on success; None on invalid IPv4 input.
**Notes**:
- No validation is performed regarding whether the IPv4 address is public or private; any syntactically valid IPv4 address is accepted.

---

## Function: in6_6to4ExtractAddr

```python
def in6_6to4ExtractAddr(addr)
```

**in6_6to4ExtractAddr**: Extract the embedded IPv4 address from a 6to4 IPv6 address (2002::/16).
**Signature**: def in6_6to4ExtractAddr(addr: str) -> Optional[str]
**Parameters**:
- addr (str): IPv6 address string expected to be a 6to4 address.
**Behavior**:
- Attempt to parse addr as an IPv6 address using inet_pton(AF_INET6, addr).
- If parsing fails (any exception), return None.
- Verify the address is 6to4:
- If the first two bytes of the parsed IPv6 address are not exactly b" \x02" (0x20 0x02), return None.
- Extract bytes 2..5 (inclusive of start, exclusive of end; i.e., baddr[2:6]) as the embedded IPv4 address.
- Convert those 4 bytes to printable IPv4 form using inet_ntop(AF_INET, ...) and return it.
**Returns**:
- Optional[str]: The extracted IPv4 address string if addr is valid IPv6 and within 2002::/16; otherwise None.

---

## Function: in6_getLocalUniquePrefix

```python
def in6_getLocalUniquePrefix()
```

**in6_getLocalUniquePrefix**: Generate a pseudo-random IPv6 Unique Local Address (ULA) prefix following RFC 4193 section 3.2.2 guidance.
**Signature**: def in6_getLocalUniquePrefix() -> str
**Parameters**:
- (none)
**Behavior**:
- Obtain the current time-of-day as a floating-point value using time.time().
- Split this timestamp into two 32-bit components:
- i: the integer seconds part (int(tod)).
- j: the fractional part scaled to a 32-bit fraction: int((tod - i) * (2**32)).
- Pack i and j as two big-endian unsigned 32-bit integers using struct.pack("!II", i, j), producing an 8-byte value btod.
- Generate a random MAC address using RandMAC(); convert it to its string form.
- Convert that MAC string into a modified EUI-64 interface identifier string using in6_mactoifaceid(str(mac)).
- Convert the EUI-64 string into bytes by parsing the IPv6 address "::" + eui64_string with inet_pton(AF_INET6, ...), then take the last 8 bytes (offset 8..15) as eui64 bytes.
- Compute a SHA-1 digest over the concatenation btod + eui64_bytes.
- Take the first 5 bytes of the SHA-1 digest as the "global ID".
- Construct a 16-byte IPv6 address:
- First byte: 0xfd (indicating locally assigned ULA prefix).
- Next 5 bytes: the computed global ID.
- Remaining 10 bytes: all zeros.
- Convert this 16-byte value to printable IPv6 form using inet_ntop(AF_INET6, ...) and return it.
**Returns**:
- str: A printable IPv6 address representing the generated ULA prefix with the lower 80 bits set to zero (i.e., a /48-like prefix encoded as an address).
**Notes**:
- The time value is used directly from the system epoch (no conversion to the NTP 1900 epoch is performed).

---

## Function: in6_getRandomizedIfaceId

```python
def in6_getRandomizedIfaceId(ifaceid, previous=None)
```

**in6_getRandomizedIfaceId**: Generate an RFC 3041-style randomized IPv6 interface identifier and a new history value from a stable modified EUI-64 IID and optional previous history.
**Signature**: def in6_getRandomizedIfaceId(ifaceid: str, previous: Optional[str] = None) -> Tuple[str, str]
**Parameters**:
- ifaceid (str): Interface identifier in printable IPv6 hextet form representing 64 bits (e.g., "20b:93ff:feeb:2d3"); it is parsed by prepending "::" and taking the last 8 bytes.
- previous (Optional[str]): Previous history value in the same printable 64-bit form; if None, an 8-byte random value is used.
**Behavior**:
- Determine b_previous (8 bytes):
- If previous is None, generate 8 random bytes using RandBin(8) and convert to bytes.
- Else parse "::" + previous as IPv6 using inet_pton(AF_INET6, ...), then take the last 8 bytes.
- Parse ifaceid similarly:
- Parse "::" + ifaceid as IPv6 using inet_pton(AF_INET6, ...), then take the last 8 bytes.
- Concatenate ifaceid_bytes + b_previous to form a 16-byte input.
- Compute the MD5 digest of that 16-byte input, yielding 16 bytes.
- Split the digest into two 8-byte halves:
- s1 = digest[0:8] (future randomized IID bytes)
- s2 = digest[8:16] (future history bytes)
- Clear a specific bit in the first byte of s1:
- Replace the first byte with (first_byte & (~0x04)) while keeping the remaining 7 bytes unchanged.
- Convert s1 and s2 into printable 64-bit interface-id strings:
- For each half (s1 and s2), build a 16-byte IPv6 address consisting of 8 bytes of 0xff followed by the 8-byte half.
- Convert to printable IPv6 using inet_ntop(AF_INET6, ...).
- Take the substring starting at character index 20 of that printable string (i.e., drop the leading "ffff:ffff" portion), yielding a compact printable representation of the last 64 bits.
- Return a 2-tuple (randomized_ifaceid_str, history_str) corresponding to s1 and s2 conversions.
**Returns**:
- Tuple[str, str]: (randomized interface identifier, new history value), both as printable strings representing 64-bit values.
**Notes**:
- The function does not catch parsing errors for ifaceid/previous; invalid strings will raise exceptions from inet_pton.
- The bit-clearing operation is exactly AND with bitmask ~0x04 on the first byte of s1.

---

## Function: in6_ctop

```python
def in6_ctop(addr)
```

**in6_ctop**: Convert an IPv6 address from RFC 1924 compact base-85 notation (20 characters) into standard printable IPv6 notation.
**Signature**: def in6_ctop(addr: str) -> Optional[str]
**Parameters**:
- addr (str): RFC 1924 compact representation string; must be exactly 20 characters, each drawn from the module’s RFC1924 alphabet.
**Behavior**:
- Validate input:
- If addr length is not exactly 20, return None.
- If any character in addr is not present in the RFC1924 alphabet list (_rfc1924map), return None.
- Decode base-85:
- Initialize an integer accumulator i = 0.
- For each character c in addr (left to right):
- Find its digit value j as the index of c in _rfc1924map.
- Update i = 85 * i + j.
- Convert the resulting integer into 16 bytes (big-endian) by repeatedly taking 32-bit chunks:
- Create an empty list res.
- Repeat 4 times:
- Append struct.pack("!I", i % 2**32) to res.
- Update i = i // (2**32).
- Reverse res (because chunks were collected least-significant first).
- Concatenate the 4 packed chunks to form a 16-byte IPv6 address.
- Convert the 16-byte IPv6 address to printable form using inet_ntop(AF_INET6, ...) and return it.
**Returns**:
- Optional[str]: Printable IPv6 address on success; None if validation fails.
**Notes**:
- Character-to-digit conversion uses a linear search via _rfc1924map.index(c) for each character.

---

## Function: in6_ptoc

```python
def in6_ptoc(addr)
```

**in6_ptoc**: Convert an IPv6 address from standard printable notation into RFC 1924 compact base-85 notation.
**Signature**: def in6_ptoc(addr: str) -> Optional[str]
**Parameters**:
- addr (str): Printable IPv6 address string.
**Behavior**:
- Parse addr as IPv6 using inet_pton(AF_INET6, addr) and unpack into four big-endian unsigned 32-bit integers using struct.unpack("!IIII", ...).
- If parsing/unpacking fails (any exception), return None.
- Reconstruct the 128-bit integer value rem from the four 32-bit words:
- Use weights m = [2**96, 2**64, 2**32, 1].
- Initialize rem = 0.
- For i in 0..3: rem += d[i] * m[i].
- Convert rem to base-85 using the RFC1924 alphabet:
- Initialize an empty list of characters res.
- While rem is non-zero:
- Append _rfc1924map[rem % 85] to res.
- Update rem = rem // 85.
- Reverse res and join into a string.
- Return the resulting string.
**Returns**:
- Optional[str]: RFC 1924 compact representation string; returns an empty string when addr is "::" (because rem becomes 0 and the loop never runs); returns None on invalid IPv6 input.
**Notes**:
- No left-padding is performed to 20 characters; output length depends on the numeric value (except that "::" yields "").

---

## Function: in6_isaddr6to4

```python
def in6_isaddr6to4(x)
```

**in6_isaddr6to4**: Determine whether a printable IPv6 address is a 6to4 address (2002::/16).
**Signature**: def in6_isaddr6to4(x: str) -> bool
**Parameters**:
- x (str): Printable IPv6 address string.
**Behavior**:
- Parse x into 16 bytes using inet_pton(AF_INET6, x).
- Return True if the first two bytes are exactly 0x20 0x02 (b" \x02"), else return False.
**Returns**:
- bool: True when x is within 2002::/16; otherwise False.
**Notes**:
- No exception handling is performed; invalid IPv6 strings will raise from inet_pton.

---

## Function: in6_isaddrTeredo

```python
def in6_isaddrTeredo(x)
```

**in6_isaddrTeredo**: Determine whether a printable IPv6 address is under the configured Teredo /32 prefix (default 2001::/32).
**Signature**: def in6_isaddrTeredo(x: str) -> bool
**Parameters**:
- x (str): Printable IPv6 address string to test.
**Behavior**:
- Parse x as IPv6 and take its first 4 bytes.
- Parse conf.teredoPrefix as IPv6 and take its first 4 bytes.
- Compare these 4-byte prefixes for equality.
- Return the comparison result.
**Returns**:
- bool: True if x shares the same first 32 bits as conf.teredoPrefix; otherwise False.
**Notes**:
- No exception handling is performed; invalid IPv6 strings for x or conf.teredoPrefix will raise from inet_pton.
- The check is strictly /32 (first 4 bytes), regardless of any longer prefix semantics.

---

## Function: teredoAddrExtractInfo

```python
def teredoAddrExtractInfo(x)
```

**teredoAddrExtractInfo**: Extract Teredo server IPv4, flags, mapped IPv4, and mapped UDP port from a Teredo IPv6 address.
**Signature**: def teredoAddrExtractInfo(x: str) -> Tuple[str, int, str, int]
**Parameters**:
- x (str): Printable IPv6 address string interpreted as a Teredo address; no validation of Teredo prefix is performed.
**Behavior**:
- Parse x into 16 bytes using inet_pton(AF_INET6, x).
- Extract and decode fields by fixed offsets:
- Teredo server IPv4 address:
- Take bytes 4..7 (addr[4:8]) and convert to printable IPv4 using inet_ntop(AF_INET, ...).
- Flags:
- Take bytes 8..9 (addr[8:10]) and unpack as an unsigned 16-bit big-endian integer using struct.unpack("!H", ...)[0].
- Mapped (obfuscated) UDP port:
- Take bytes 10..11 (addr[10:12]), XOR each byte with 0xff (i.e., XOR with b"\xff\xff"), then unpack as unsigned 16-bit big-endian to get mappedport.
- Mapped (obfuscated) IPv4 address:
- Take bytes 12..15 (addr[12:16]), XOR each byte with 0xff (i.e., XOR with b"\xff\xff\xff\xff"), then convert to printable IPv4 using inet_ntop(AF_INET, ...).
- Return a 4-tuple (server, flag, mappedaddr, mappedport).
**Returns**:
- Tuple[str, int, str, int]: (Teredo server IPv4 string, flags integer, de-obfuscated mapped IPv4 string, de-obfuscated mapped UDP port integer).
**Notes**:
- No exception handling is performed; invalid IPv6 input will raise from inet_pton.
- The de-obfuscation is performed via bytewise XOR with 0xff for the port and mapped IPv4 fields.

---

## Function: in6_iseui64

```python
def in6_iseui64(x)
```

**in6_iseui64**: Determine whether an IPv6 address has a modified EUI-64 interface identifier (contains the FF:FE pattern in the IID).
**Signature**: def in6_iseui64(x: str) -> bool
**Parameters**:
- x (str): IPv6 address in printable text form (must be parseable as an IPv6 address).
**Behavior**:
- Parse the constant IPv6 address string "::ff:fe00:0" into 16-byte network form; this constant has the FF:FE marker positioned in the interface identifier portion.
- Parse the input address string x into 16-byte network form.
- Compute a bitwise AND between the parsed input bytes and the constant bytes.
- Compare the AND result to the constant bytes.
- If they are equal, the input address matches the modified EUI-64 marker pattern and the function returns True; otherwise return False.
- Any parsing error from converting x to network form propagates (no internal exception handling).
**Returns**:
- bool: True if (packed_x AND packed("::ff:fe00:0")) equals packed("::ff:fe00:0"); otherwise False.
**Notes**:
- This is a pattern test based on bitwise masking, not a full semantic validation of an EUI-64-derived IID beyond the FF:FE marker presence.

---

## Function: in6_isanycast

```python
def in6_isanycast(x)
```

**in6_isanycast**: Check whether an IPv6 address is an anycast address using the RFC 2526 EUI-64-based anycast format (non-EUI-64 case is not implemented).
**Signature**: def in6_isanycast(x: str) -> bool
**Parameters**:
- x (str): IPv6 address in printable text form.
**Behavior**:
- First call in6_iseui64(x).
- If in6_iseui64(x) is True:
- Define the mask/pattern address string s = "::fdff:ffff:ffff:ff80".
- Convert x and s to 16-byte network form.
- Compute bitwise AND of packed_x with packed_s.
- Return True if the AND result equals packed_s; otherwise return False.
- If in6_iseui64(x) is False:
- Emit a warning with the exact message "in6_isanycast(): TODO not EUI-64".
- Return False.
- Any parsing error from converting x (or s) to network form propagates in the EUI-64 branch (no internal exception handling).
**Returns**:
- bool: True only for addresses that both (1) match the modified EUI-64 marker and (2) satisfy the RFC2526 EUI-64 anycast bit-pattern test; otherwise False.
**Notes**:
- The non-EUI-64 anycast format described in comments is explicitly not implemented; the function always returns False for non-EUI-64 addresses.

---

## Function: in6_or

```python
def in6_or(a1, a2)
```

**in6_or**: Compute a bytewise bit-to-bit OR between two IPv6 addresses in network-byte (packed) form.
**Signature**: def in6_or(a1: bytes, a2: bytes) -> bytes
**Parameters**:
- a1 (bytes): First packed address/bitstring.
- a2 (bytes): Second packed address/bitstring; must be the same length as a1 for meaningful results.
**Behavior**:
- Perform a bitwise OR across corresponding bytes of a1 and a2.
- Return the resulting bytes object.
- The function delegates the operation to scapy.utils.stror.
**Returns**:
- bytes: The OR-combined byte string.
**Notes**:
- Although documented for IPv6 (16 bytes), the underlying operation is a generic byte-string OR; callers are responsible for providing appropriately sized packed addresses.

---

## Function: in6_and

```python
def in6_and(a1, a2)
```

**in6_and**: Compute a bytewise bit-to-bit AND between two IPv6 addresses in network-byte (packed) form.
**Signature**: def in6_and(a1: bytes, a2: bytes) -> bytes
**Parameters**:
- a1 (bytes): First packed address/bitstring.
- a2 (bytes): Second packed address/bitstring; must be the same length as a1 for meaningful results.
**Behavior**:
- Perform a bitwise AND across corresponding bytes of a1 and a2.
- Return the resulting bytes object.
- The function delegates the operation to scapy.utils.strand.
**Returns**:
- bytes: The AND-combined byte string.
**Notes**:
- Although documented for IPv6 (16 bytes), the underlying operation is a generic byte-string AND; callers are responsible for providing appropriately sized packed addresses.

---

## Function: in6_xor

```python
def in6_xor(a1, a2)
```

**in6_xor**: Compute a bytewise bit-to-bit XOR between two IPv6 addresses in network-byte (packed) form.
**Signature**: def in6_xor(a1: bytes, a2: bytes) -> bytes
**Parameters**:
- a1 (bytes): First packed address/bitstring.
- a2 (bytes): Second packed address/bitstring; must be the same length as a1 for meaningful results.
**Behavior**:
- Perform a bitwise XOR across corresponding bytes of a1 and a2.
- Return the resulting bytes object.
- The function delegates the operation to scapy.utils.strxor.
**Returns**:
- bytes: The XOR-combined byte string.
**Notes**:
- Although documented for IPv6 (16 bytes), the underlying operation is a generic byte-string XOR; callers are responsible for providing appropriately sized packed addresses.

---

## Function: in6_cidr2mask

```python
def in6_cidr2mask(m)
```

**in6_cidr2mask**: Convert an IPv6 CIDR prefix length into a 16-byte network-order mask.
**Signature**: def in6_cidr2mask(m: int) -> bytes
**Parameters**:
- m (int): Prefix length in bits; must be within 0..128 inclusive.
**Behavior**:
- Validate that m is within [0, 128].
- If m > 128 or m < 0, raise Scapy_Exception with message: "value provided to in6_cidr2mask outside [0, 128] domain (%d)" % m.
- Build a list of four 32-bit unsigned integers representing the mask, from most-significant 32-bit block to least-significant:
- Initialize an empty list t.
- Repeat for i = 0..3:
- Let block_bits = min(32, m).
- Compute the 32-bit mask value for this block as max(0, 2**32 - 2**(32 - block_bits)).
- This yields 0 when block_bits is 0, and 0xFFFFFFFF when block_bits is 32.
- Append that integer to t.
- Subtract 32 from m (m -= 32) before the next iteration.
- Pack each integer in t using struct.pack('!I', x) (big-endian 32-bit) and concatenate the four packed blocks to produce 16 bytes.
**Returns**:
- bytes: A 16-byte IPv6 netmask with the top original prefix-length bits set to 1 and the remaining bits set to 0.
**Notes**:
- The function always returns exactly 16 bytes.
- The computation is performed in 32-bit chunks; correctness relies on the specific formula used for each chunk.

---

## Function: in6_mask2cidr

```python
def in6_mask2cidr(m)
```

**in6_mask2cidr**: Convert a 16-byte IPv6 netmask into the corresponding CIDR prefix length.
**Signature**: def in6_mask2cidr(m: bytes) -> int
**Parameters**:
- m (bytes): IPv6 netmask in network form; must be exactly 16 bytes.
**Behavior**:
- Validate that len(m) == 16.
- If not, raise Scapy_Exception with message "value must be 16 octets long".
- Interpret the mask as four consecutive big-endian 32-bit unsigned integers.
- Scan bits from most significant to least significant:
- For each 32-bit block index i from 0 to 3:
- Unpack s = struct.unpack('!I', m[i*4:(i+1)*4])[0].
- For bit position j from 0 to 31 (where j=0 corresponds to the most significant bit of the block):
- Test whether the bit (1 << (31 - j)) is set in s.
- On the first bit that is not set, immediately return the prefix length i*32 + j.
- If all 128 bits are set (no zero bit found), return 128.
**Returns**:
- int: The index (count) of leading 1 bits up to the first 0 bit; returns 128 if the mask is all ones.
**Notes**:
- The function does not validate that the mask is contiguous (i.e., it does not check for 1s appearing after a 0); it simply returns the position of the first 0 bit.

---

## Function: in6_getnsma

```python
def in6_getnsma(a)
```

**in6_getnsma**: Compute the solicited-node multicast IPv6 address (ff02::1:ffXX:XXXX) corresponding to a given IPv6 address.
**Signature**: def in6_getnsma(a: bytes) -> bytes
**Parameters**:
- a (bytes): IPv6 address in 16-byte network form.
**Behavior**:
- Compute r as the bitwise AND of a with the packed mask for "::ff:ffff".
- This keeps only the low 24 bits of the address (last 3 bytes) and clears the rest.
- Compute r as the bitwise OR of packed("ff02::1:ff00:0") with the previous r.
- This sets the multicast prefix ff02::1:ff00:0 and inserts the extracted low 24 bits.
- Return r as 16-byte network form.
**Returns**:
- bytes: The 16-byte packed solicited-node multicast address derived from a.
**Notes**:
- The function assumes a is a valid 16-byte IPv6 packed address; errors from incorrect length depend on the underlying bitwise helpers.

---

## Function: in6_getnsmac

```python
def in6_getnsmac(a)
```

**in6_getnsmac**: Derive the Ethernet multicast MAC address (33:33:xx:xx:xx:xx) corresponding to a given IPv6 multicast address.
**Signature**: def in6_getnsmac(a: bytes) -> str
**Parameters**:
- a (bytes): IPv6 address in 16-byte network form.
**Behavior**:
- Unpack the 16 bytes of a as 16 unsigned bytes using struct.unpack('16B', a).
- Take the last 4 unpacked bytes.
- Build a MAC address string:
- Start with the literal prefix "33:33:".
- Append the last 4 bytes formatted as two-digit lowercase hexadecimal separated by ':' ("%.2x" for each byte).
- Return the resulting string.
**Returns**:
- str: A MAC address string of the form "33:33:xx:xx:xx:xx".
**Notes**:
- This function does not validate that the IPv6 address is multicast; it mechanically maps the last 32 bits into the MAC per the standard IPv6 multicast-to-Ethernet mapping.

---

## Function: in6_getha

```python
def in6_getha(prefix)
```

**in6_getha**: Compute the anycast address for “all home agents” on a given subnet prefix.
**Signature**: def in6_getha(prefix: str) -> str
**Parameters**:
- prefix (str): IPv6 address/prefix in printable form; only the top 64 bits are used.
**Behavior**:
- Convert prefix to 16-byte network form.
- Compute the /64 network portion by ANDing the packed prefix with the 16-byte mask produced by in6_cidr2mask(64).
- OR the result with the packed constant "::fdff:ffff:ffff:fffe".
- This sets the interface identifier portion to the fixed anycast value used for home agents.
- Convert the final 16-byte address back to printable IPv6 text form and return it.
- Any parsing errors from converting prefix propagate (no internal exception handling).
**Returns**:
- str: The printable IPv6 anycast address for all home agents on the /64 containing prefix.

---

## Function: in6_ptop

```python
def in6_ptop(str)
```

**in6_ptop**: Normalize an IPv6 address string to its canonical printable form.
**Signature**: str in6_ptop(str: str)
**Parameters**:
- str (str): IPv6 address in printable text form; must be parseable as an IPv6 address.
**Behavior**:
- Parse the input IPv6 address string into its 16-byte network/binary form using IPv6 parsing.
- Convert that 16-byte form back into a printable IPv6 string using IPv6 formatting.
- The returned string is the normalized representation produced by the formatter (e.g., compressing zeros, removing leading zeros in hextets).
- If the input is not a valid IPv6 address string, the underlying parser raises an exception (this function does not catch it).
**Returns**:
- str: The normalized printable IPv6 address corresponding to the input.
**Notes**:
- Normalization is performed by a parse-then-format round trip; the exact formatting matches the platform/library IPv6 formatter used.

---

## Function: in6_isincluded

```python
def in6_isincluded(addr, prefix, plen)
```

**in6_isincluded**: Test whether an IPv6 address belongs to a given IPv6 prefix of a specified length.
**Signature**: bool in6_isincluded(addr: str, prefix: str, plen: int)
**Parameters**:
- addr (str): IPv6 address in printable form to test.
- prefix (str): IPv6 prefix base address in printable form.
- plen (int): Prefix length in bits; passed to the IPv6 CIDR-to-mask routine.
**Behavior**:
- Convert addr from printable form to 16-byte network form.
- Build a 16-byte mask corresponding to plen bits (using the module’s IPv6 CIDR mask generator).
- Convert prefix from printable form to 16-byte network form.
- Compute the bitwise AND of the binary addr with the mask.
- Compare the AND result to the binary prefix for exact equality.
- Return True if equal, otherwise False.
- Any parsing errors for addr/prefix or invalid plen handling propagate as exceptions from the called routines (this function does not catch them).
**Returns**:
- bool: True if addr is within prefix/plen, else False.
**Notes**:
- Membership is determined purely by masking and equality; no normalization of prefix beyond binary parsing is performed.

---

## Function: in6_isllsnmaddr

```python
def in6_isllsnmaddr(str)
```

**in6_isllsnmaddr**: Check whether an IPv6 address is a link-local solicited-node multicast address (ff02::1:ff00:0/104).
**Signature**: bool in6_isllsnmaddr(str: str)
**Parameters**:
- str (str): IPv6 address in printable form to test.
**Behavior**:
- Parse the input address string into 16-byte network form.
- Apply a fixed 16-byte mask that keeps the first 13 bytes and clears the last 3 bytes (mask = 13 bytes of 0xFF followed by 3 bytes of 0x00).
- Bitwise-AND the parsed address with that mask.
- Compare the result to the constant 16-byte prefix value corresponding to ff02::1:ff00:0 with the last 3 bytes zeroed (binary constant: ff 02 00 00 00 00 00 00 00 00 00 01 ff 00 00 00).
- Return True if equal, else False.
- If the input is not a valid IPv6 address string, parsing raises an exception (not caught here).
**Returns**:
- bool: True if the address is within ff02::1:ff00:0/104, otherwise False.

---

## Function: in6_isdocaddr

```python
def in6_isdocaddr(str)
```

**in6_isdocaddr**: Determine whether an IPv6 address is in the documentation prefix 2001:db8::/32.
**Signature**: bool in6_isdocaddr(str: str)
**Parameters**:
- str (str): IPv6 address in printable form to test.
**Behavior**:
- Delegate to the generic inclusion test using:
- Prefix = '2001:db8::'
- Prefix length = 32
- Return whatever the inclusion test returns.
- Any exceptions from parsing or mask generation propagate.
**Returns**:
- bool: True if the address is within 2001:db8::/32, else False.

---

## Function: in6_islladdr

```python
def in6_islladdr(str)
```

**in6_islladdr**: Determine whether an IPv6 address is in the allocated link-local unicast prefix fe80::/10.
**Signature**: bool in6_islladdr(str: str)
**Parameters**:
- str (str): IPv6 address in printable form to test.
**Behavior**:
- Delegate to the generic inclusion test using:
- Prefix = 'fe80::'
- Prefix length = 10
- Return whatever the inclusion test returns.
- Any exceptions from parsing or mask generation propagate.
**Returns**:
- bool: True if the address is within fe80::/10, else False.

---

## Function: in6_issladdr

```python
def in6_issladdr(str)
```

**in6_issladdr**: Determine whether an IPv6 address is in the (deprecated) site-local prefix fec0::/10.
**Signature**: bool in6_issladdr(str: str)
**Parameters**:
- str (str): IPv6 address in printable form to test.
**Behavior**:
- Delegate to the generic inclusion test using:
- Prefix = 'fec0::'
- Prefix length = 10
- Return whatever the inclusion test returns.
- Any exceptions from parsing or mask generation propagate.
**Returns**:
- bool: True if the address is within fec0::/10, else False.
**Notes**:
- This prefix is deprecated/reserved; the function remains for historical compatibility.

---

## Function: in6_isuladdr

```python
def in6_isuladdr(str)
```

**in6_isuladdr**: Determine whether an IPv6 address is in the Unique Local Address (ULA) prefix fc00::/7.
**Signature**: bool in6_isuladdr(str: str)
**Parameters**:
- str (str): IPv6 address in printable form to test.
**Behavior**:
- Delegate to the generic inclusion test using:
- Prefix = 'fc00::'
- Prefix length = 7
- Return whatever the inclusion test returns.
- Any exceptions from parsing or mask generation propagate.
**Returns**:
- bool: True if the address is within fc00::/7, else False.

---

## Function: in6_isgladdr

```python
def in6_isgladdr(str)
```

**in6_isgladdr**: Determine whether an IPv6 address is in the allocated global unicast prefix 2000::/3.
**Signature**: bool in6_isgladdr(str: str)
**Parameters**:
- str (str): IPv6 address in printable form to test.
**Behavior**:
- Delegate to the generic inclusion test using:
- Prefix = '2000::'
- Prefix length = 3
- Return whatever the inclusion test returns.
- Any exceptions from parsing or mask generation propagate.
**Returns**:
- bool: True if the address is within 2000::/3, else False.
**Notes**:
- Unique Local Addresses (fc00::/7) are not part of 2000::/3 and therefore will not match.

---

## Function: in6_ismaddr

```python
def in6_ismaddr(str)
```

**in6_ismaddr**: Determine whether an IPv6 address is in the multicast prefix ff00::/8.
**Signature**: bool in6_ismaddr(str: str)
**Parameters**:
- str (str): IPv6 address in printable form to test.
**Behavior**:
- Delegate to the generic inclusion test using:
- Prefix = 'ff00::'
- Prefix length = 8
- Return whatever the inclusion test returns.
- Any exceptions from parsing or mask generation propagate.
**Returns**:
- bool: True if the address is within ff00::/8, else False.

---

## Function: in6_ismnladdr

```python
def in6_ismnladdr(str)
```

**in6_ismnladdr**: Determine whether an IPv6 address is in the node-local multicast prefix ff01::/16.
**Signature**: bool in6_ismnladdr(str: str)
**Parameters**:
- str (str): IPv6 address in printable form to test.
**Behavior**:
- Delegate to the generic inclusion test using:
- Prefix = 'ff01::'
- Prefix length = 16
- Return whatever the inclusion test returns.
- Any exceptions from parsing or mask generation propagate.
**Returns**:
- bool: True if the address is within ff01::/16, else False.

---

## Function: in6_ismgladdr

```python
def in6_ismgladdr(str)
```

**in6_ismgladdr**: Test whether an IPv6 address string is in the global-scope multicast range ff0e::/16.
**Signature**: def in6_ismgladdr(str) -> bool
**Parameters**:
- str (str): IPv6 address in printable text form.
**Behavior**:
- Determine whether the given address belongs to the IPv6 prefix ff0e::/16.
- Perform the check by delegating to the generic IPv6 prefix-membership test with:
- prefix = "ff0e::"
- prefix length = 16
- The membership test converts the address and prefix to 16-byte network form, builds a /16 mask, ANDs the address with the mask, and compares the result to the masked prefix.
- Any parsing error raised by IPv6 text-to-binary conversion propagates to the caller (this function does not catch exceptions).
**Returns**:
- bool: True if the address is within ff0e::/16, otherwise False.

---

## Function: in6_ismlladdr

```python
def in6_ismlladdr(str)
```

**in6_ismlladdr**: Test whether an IPv6 address string is in the link-local-scope multicast range ff02::/16.
**Signature**: def in6_ismlladdr(str) -> bool
**Parameters**:
- str (str): IPv6 address in printable text form.
**Behavior**:
- Determine whether the given address belongs to the IPv6 prefix ff02::/16.
- Perform the check by delegating to the generic IPv6 prefix-membership test with:
- prefix = "ff02::"
- prefix length = 16
- The membership test converts the address and prefix to 16-byte network form, builds a /16 mask, ANDs the address with the mask, and compares the result to the masked prefix.
- Any parsing error raised by IPv6 text-to-binary conversion propagates to the caller (this function does not catch exceptions).
**Returns**:
- bool: True if the address is within ff02::/16, otherwise False.

---

## Function: in6_ismsladdr

```python
def in6_ismsladdr(str)
```

**in6_ismsladdr**: Test whether an IPv6 address string is in the site-local-scope multicast range ff05::/16 (deprecated scope, kept for historical reasons).
**Signature**: def in6_ismsladdr(str) -> bool
**Parameters**:
- str (str): IPv6 address in printable text form.
**Behavior**:
- Determine whether the given address belongs to the IPv6 prefix ff05::/16.
- Perform the check by delegating to the generic IPv6 prefix-membership test with:
- prefix = "ff05::"
- prefix length = 16
- The membership test converts the address and prefix to 16-byte network form, builds a /16 mask, ANDs the address with the mask, and compares the result to the masked prefix.
- Any parsing error raised by IPv6 text-to-binary conversion propagates to the caller (this function does not catch exceptions).
**Returns**:
- bool: True if the address is within ff05::/16, otherwise False.
**Notes**:
- Site-local multicast scope is deprecated; this function exists for compatibility.

---

## Function: in6_isaddrllallnodes

```python
def in6_isaddrllallnodes(str)
```

**in6_isaddrllallnodes**: Test whether an IPv6 address string is exactly the link-local all-nodes multicast address ff02::1.
**Signature**: def in6_isaddrllallnodes(str) -> bool
**Parameters**:
- str (str): IPv6 address in printable text form.
**Behavior**:
- Convert the constant address "ff02::1" to 16-byte network form.
- Convert the provided address string to 16-byte network form.
- Compare the two 16-byte values for exact equality.
- Any parsing error raised by IPv6 text-to-binary conversion propagates to the caller (this function does not catch exceptions).
**Returns**:
- bool: True if the address is exactly ff02::1, otherwise False.

---

## Function: in6_isaddrllallservers

```python
def in6_isaddrllallservers(str)
```

**in6_isaddrllallservers**: Test whether an IPv6 address string is exactly the link-local all-servers multicast address ff02::2.
**Signature**: def in6_isaddrllallservers(str) -> bool
**Parameters**:
- str (str): IPv6 address in printable text form.
**Behavior**:
- Convert the constant address "ff02::2" to 16-byte network form.
- Convert the provided address string to 16-byte network form.
- Compare the two 16-byte values for exact equality.
- Any parsing error raised by IPv6 text-to-binary conversion propagates to the caller (this function does not catch exceptions).
**Returns**:
- bool: True if the address is exactly ff02::2, otherwise False.

---

## Function: in6_getscope

```python
def in6_getscope(addr)
```

**in6_getscope**: Classify an IPv6 address string into a scope constant (global/link-local/site-local/loopback) or -1 if unknown.
**Signature**: def in6_getscope(addr) -> int
**Parameters**:
- addr (str): IPv6 address in printable text form.
**Behavior**:
- Determine scope using the following ordered checks:
- If the address is in allocated global unicast space (2000::/3) or in unique-local space (fc00::/7), set scope to IPV6_ADDR_GLOBAL.
- Else if the address is in allocated link-local unicast space (fe80::/10), set scope to IPV6_ADDR_LINKLOCAL.
- Else if the address is in allocated site-local unicast space (fec0::/10, deprecated), set scope to IPV6_ADDR_SITELOCAL.
- Else if the address is multicast (ff00::/8), refine by multicast scope:
- If it is global multicast (ff0e::/16), set scope to IPV6_ADDR_GLOBAL.
- Else if it is link-local multicast (ff02::/16), set scope to IPV6_ADDR_LINKLOCAL.
- Else if it is site-local multicast (ff05::/16), set scope to IPV6_ADDR_SITELOCAL.
- Else if it is node-local multicast (ff01::/16), set scope to IPV6_ADDR_LOOPBACK.
- Else set scope to -1.
- Else if the address string is exactly "::1", set scope to IPV6_ADDR_LOOPBACK.
- Else set scope to -1.
- Return the computed scope.
- Any parsing error raised by the helper prefix-membership checks (which parse IPv6 text) propagates to the caller; this function does not catch exceptions.
**Returns**:
- int: One of the IPV6_ADDR_* scope constants as above, or -1 when the scope cannot be determined by these rules.
**Notes**:
- Unique-local addresses are treated as global scope by this function.

---

## Function: in6_get_common_plen

```python
def in6_get_common_plen(a, b)
```

**in6_get_common_plen**: Compute the length (in bits) of the longest common prefix shared by two IPv6 address strings.
**Signature**: def in6_get_common_plen(a, b) -> int
**Parameters**:
- a (str): First IPv6 address in printable text form.
- b (str): Second IPv6 address in printable text form.
**Behavior**:
- Convert both address strings to 16-byte network form using IPv6 text-to-binary conversion.
- Compare the two 16-byte sequences from the first byte to the last:
- For each byte index i from 0 to 15:
- Compute how many leading bits match within that byte (0 to 8) by scanning bit positions from most-significant to least-significant:
- For bit offset k from 0 to 7:
- Build mask = 0x80 >> k.
- If (byte_a & mask) differs from (byte_b & mask), then the number of matching bits in this byte is k; stop scanning this byte.
- If no difference is found, the number of matching bits in this byte is 8.
- If the matching-bit count for this byte is not 8, return (8 * i + matching_bits_in_byte) immediately.
- If all 16 bytes match completely, return 128.
- Any parsing error raised by IPv6 text-to-binary conversion propagates to the caller.
**Returns**:
- int: An integer in [0, 128] giving the common prefix length in bits.

---

## Function: matching_bits

```python
def matching_bits(byte1, byte2)
```

**matching_bits**: Compute how many leading (most-significant) bits are identical between two 8-bit integers.
**Signature**: def matching_bits(byte1, byte2)
**Parameters**:
- byte1 (byte1): Not defined in this module as a top-level callable; the only implementation present is a nested helper inside in6_get_common_plen.
- byte2 (byte2): Not defined in this module as a top-level callable; the only implementation present is a nested helper inside in6_get_common_plen.
**Behavior**:
- (Not a top-level function in this module.) The only defined behavior is as an inner function within in6_get_common_plen:
- Iterate i from 0 to 7, using mask = 0x80 >> i.
- Return i at the first position where (byte1 & mask) != (byte2 & mask).
- If all 8 bits match, return 8.
**Returns**:
- (Not applicable): This entity is not implemented as a module-level function in the provided module; only the nested helper exists.
**Notes**:
- Because there is no module-level definition, importing utils6.matching_bits would fail; only in6_get_common_plen’s internal helper performs this operation.

---

## Function: in6_isvalid

```python
def in6_isvalid(address)
```

**in6_isvalid**: Validate whether a string is syntactically a valid IPv6 address.
**Signature**: def in6_isvalid(address) -> bool
**Parameters**:
- address (str): Candidate IPv6 address string.
**Behavior**:
- Attempt to parse the string as an IPv6 address using IPv6 text-to-binary conversion.
- If parsing succeeds, return True.
- If any exception is raised during parsing, catch it and return False.
- No other side effects.
**Returns**:
- bool: True if parsing as IPv6 succeeds, otherwise False.
