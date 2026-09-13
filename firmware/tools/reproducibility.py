"""Compare artifacts without mistaking the same build for independent evidence."""
import hashlib
from pathlib import Path


def compare(work, comparison, artifacts):
    roots=[Path(work).resolve(),Path(comparison).resolve()]
    if roots[0]==roots[1] or roots[0].is_relative_to(roots[1]) or roots[1].is_relative_to(roots[0]):
        raise ValueError('Reproduction requires two separate project directories')
    builds=[]
    for root in roots:
        build=(root/'build').resolve()
        if not build.is_relative_to(root):
            raise ValueError('Build directory must belong to its project')
        cache=build/'CMakeCache.txt'
        if not cache.is_file():raise ValueError('Missing CMake configuration for reproduction')
        homes=[line.split('=',1)[1] for line in cache.read_text().splitlines() if line.startswith('CMAKE_HOME_DIRECTORY:INTERNAL=')]
        if len(homes)!=1 or Path(homes[0]).resolve()!=root:
            raise ValueError('CMake configuration belongs to a different source directory')
        builds.append(build)
    if not artifacts:raise ValueError('No artifacts to compare')
    seen=set()
    for item in artifacts:
        name=Path(item['file'])
        if name.is_absolute() or '..' in name.parts or str(name) in seen:
            raise ValueError('Invalid or duplicate reproduction artifact path')
        seen.add(str(name))
        files=[(build/name).resolve() for build in builds]
        if any(not file.is_relative_to(build) or not file.is_file() for file,build in zip(files,builds)):
            raise ValueError('Reproduction artifact missing or outside its build: '+str(name))
        if files[0].samefile(files[1]):
            raise ValueError('Reproduction artifacts share the same file: '+str(name))
        if any(hashlib.sha256(file.read_bytes()).hexdigest()!=item['sha256'] for file in files):
            raise ValueError('Reproduction artifact mismatch: '+str(name))
    return {'verified':True,'artifact_count':len(artifacts),
            'scope':'Byte-identical artifacts in two distinct CMake project/build directories. '
                    'Directory checks do not prove compiler execution; retain separate build logs. '
                    'Shared host/toolchain/registry caches and cross-machine limits must be documented.'}
