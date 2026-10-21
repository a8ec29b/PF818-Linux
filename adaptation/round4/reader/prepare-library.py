#!/usr/bin/env python3
"""Adapt the device's C-only Android reader library to the matching Linux ABI."""
from pathlib import Path
import struct
src=Path('build/round4/runtime-apk/lib/arm64-v8a/libicreader-lib.so')
b=bytearray(src.read_bytes())
phoff=struct.unpack_from('<Q',b,32)[0]
phsize,phnum=struct.unpack_from('<HH',b,54)
loads=[]
for i in range(phnum):
 p=phoff+i*phsize;typ=struct.unpack_from('<I',b,p)[0]
 off,va=struct.unpack_from('<QQ',b,p+8)
 if typ==1:loads.append((va,off,struct.unpack_from('<Q',b,p+32)[0]))
 if typ==2:dynoff,dynlen=off,struct.unpack_from('<Q',b,p+32)[0]
def offset(va):
 for start,off,size in loads:
  if start<=va<start+size:return off+va-start
entries=[struct.unpack_from('<QQ',b,p) for p in range(dynoff,dynoff+dynlen,16)]
strtab=offset(next(v for t,v in entries if t==5))
soname=next(v for t,v in entries if t==14)
b[strtab+soname:strtab+soname+10]=b'libc.so.6\0'
new=[]
for t,v in entries:
 if t==0:break
 if t in (14,0x6ffffffe,0x6fffffff,0x6ffffff0):continue
 if t==1:
  name=bytes(b[strtab+v:b.index(0,strtab+v)]).decode()
  if name in ('libm.so','libdl.so'):continue
  if name=='libc.so':v=soname
 new.append((t,v))
new.append((0,0))
for i in range(dynlen//16):
 struct.pack_into('<QQ',b,dynoff+i*16,*(new[i] if i<len(new) else (0,0)))
Path('build/round4/linux-reader/libpf818-reader.so').write_bytes(b)
