'''Build dist/moonsync.zip. Install it with:
    calibre-customize -a dist/moonsync.zip
or, while developing, build + install + launch calibre in debug mode:
    calibre-customize -b moonsync && calibre-debug -g
'''
import os
import zipfile

here = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(here, 'moonsync')
out = os.path.join(here, 'dist', 'moonsync.zip')
os.makedirs(os.path.dirname(out), exist_ok=True)
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for name in sorted(os.listdir(src)):
        if os.path.isfile(os.path.join(src, name)) and not name.endswith('.pyc'):
            z.write(os.path.join(src, name), name)
print('Wrote', out)
