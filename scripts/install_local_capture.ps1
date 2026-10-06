param(
    [string]$Python = ".\.venv\Scripts\python.exe",
    [string]$Source = "E:\Experiment\personal-predictive-ai-sources\openadapt-capture"
)

$ErrorActionPreference = "Stop"

& $Python -m pip install -e $Source
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install local openadapt-capture source."
}

& $Python -c @"
from importlib.metadata import version
parts = tuple(int(x) for x in version('openadapt-capture').split('.')[:2])
assert (1, 3) <= parts < (1, 4), version('openadapt-capture')
print('openadapt-capture', version('openadapt-capture'))
"@
if ($LASTEXITCODE -ne 0) {
    throw "openadapt-capture version must satisfy >=1.3,<1.4"
}
