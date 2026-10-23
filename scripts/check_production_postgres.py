"""Disposable Docker CI production acceptance checks. Never targets Render."""
import ast
from pathlib import Path
import subprocess

compose=['docker','compose','-f','infra/staging/compose.yml']
suite=ast.parse(Path('services/api/tests/test_production.py').read_text())
check=next(node for node in suite.body if isinstance(node,ast.FunctionDef) and node.name=='test_production_reader_and_newsroom_boundaries')
program=next(node.value.value for node in check.body if isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str))
for public,name in [('false','agn_production_private'),('true','agn_production_public')]:
    subprocess.run(compose+['exec','-T','postgres','createdb','-U','agn',name],check=True)
    try:
        subprocess.run(compose+['exec','-T','-e','AGN_NATIVE_PRODUCTION_CHECK=1','-e','PUBLIC_READER_ENABLED='+public,'api','python','-c',program],check=True)
    finally:
        subprocess.run(compose+['exec','-T','postgres','dropdb','-U','agn',name],check=True)
print('Native PostgreSQL production private/public boundaries, eight-language routes, MFA and audit checks passed.')
