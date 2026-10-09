#requires -Version 5.1
<#
One-time local signing bootstrap. The signing key NEVER leaves the local
computer except encrypted via GitHub Environment Secrets.
Requires authenticated GitHub CLI and JDK/keytool.
Usage: powershell -ExecutionPolicy Bypass -File .\scripts\agent-update\init-production-signing.ps1
Never put this file's local output, .p12, or passwords in Git.
#>
[CmdletBinding()]
param(
    [string]$Repository = 'Sharkecho/Public-Build-Farm',
    [string]$Environment = 'androidos-production',
    [string]$KeyDirectory = (Join-Path $HOME '.gpt-androidos-signing')
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
function Assert-Last($Operation) {
    if ($LASTEXITCODE -ne 0) { throw "$Operation failed (exit $LASTEXITCODE)." }
}
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'Install GitHub CLI (gh) and run gh auth login first.' }
if (-not (Get-Command keytool -ErrorAction SilentlyContinue)) { throw 'Install JDK 17+; keytool must be available on PATH.' }
& gh auth status 2>$null | Out-Null
Assert-Last 'GitHub CLI authentication'
$environmentJson = & gh api "repos/$Repository/environments/$Environment"
Assert-Last 'Read protected GitHub environment'
$settings = ($environmentJson | ConvertFrom-Json)
if ($settings.can_admins_bypass -eq $true) { throw 'Disable admin bypass for production environment first.' }
if (-not ($settings.protection_rules | Where-Object { $_.type -eq 'required_reviewers' })) { throw 'Add a required production reviewer first.' }
if ($settings.deployment_branch_policy.custom_branch_policies -ne $true) { throw 'Select explicit deployment branches and allow main only.' }
$branchJson = & gh api "repos/$Repository/environments/$Environment/deployment-branch-policies"
Assert-Last 'Read allowed deployment branches'
$rules = @((($branchJson | ConvertFrom-Json).branch_policies) | Where-Object { $null -ne $_ })
if ($rules.Count -ne 1 -or $rules[0].name -ne 'main') { throw 'Expected exactly one allowed deployment branch: main.' }

New-Item -ItemType Directory -Force -Path $KeyDirectory | Out-Null
$keyFile = Join-Path $KeyDirectory 'androidos-release.p12'
$passwordFile = Join-Path $KeyDirectory 'password.dpapi'
$alias = 'androidos'
if ((Test-Path $keyFile) -xor (Test-Path $passwordFile)) {
    throw 'Incomplete existing signing material. Refusing to overwrite or rotate signing key.'
}
if (Test-Path $keyFile) {
    $secure = Get-Content -Raw -Path $passwordFile | ConvertTo-SecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
    Write-Host 'Reusing existing local signing key (never rotating).'
} else {
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes = New-Object byte[] 48
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $password = [Convert]::ToBase64String($bytes)
    $env:ANDROIDOS_LOCAL_SIGN_PASS = $password
    try {
        & keytool -genkeypair -noprompt -keystore $keyFile -storetype PKCS12 -alias $alias -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 10000 -dname 'CN=GPT-AndroidOS,O=Personal Android Agent,C=US' -storepass:env ANDROIDOS_LOCAL_SIGN_PASS -keypass:env ANDROIDOS_LOCAL_SIGN_PASS
        Assert-Last 'Create fixed production signing key'
        ($password | ConvertTo-SecureString -AsPlainText -Force | ConvertFrom-SecureString) | Set-Content -Path $passwordFile -Encoding ASCII
    } catch {
        if (-not (Test-Path $passwordFile)) { Remove-Item -Force -ErrorAction SilentlyContinue $keyFile }
        throw
    } finally { Remove-Item Env:ANDROIDOS_LOCAL_SIGN_PASS -ErrorAction SilentlyContinue }
    Write-Host 'Created new fixed signing key. BACK UP .p12 AND its password before device installation.'
}
$env:ANDROIDOS_LOCAL_SIGN_PASS = $password
try {
    $list = (& keytool -list -v -keystore $keyFile -storetype PKCS12 -alias $alias -storepass:env ANDROIDOS_LOCAL_SIGN_PASS) -join "`n"
    Assert-Last 'Inspect signing certificate'
} finally { Remove-Item Env:ANDROIDOS_LOCAL_SIGN_PASS -ErrorAction SilentlyContinue }
if ($list -notmatch 'SHA256:\s*([0-9A-Fa-f:]{64,100})') { throw 'Unable to parse signing certificate SHA-256.' }
$fingerprint = $Matches[1].Replace(':','').ToLowerInvariant()
if ($fingerprint -notmatch '^[0-9a-f]{64}$') { throw 'Bad certificate fingerprint.' }
$existing = & gh variable list -e $Environment -R $Repository --json name,value | ConvertFrom-Json
Assert-Last 'Inspect existing environment variables'
$prior = @($existing | Where-Object { $_.name -eq 'ANDROIDOS_CERT_SHA256' })
if ($prior.Count -gt 0 -and $prior[0].value -ne $fingerprint) {
    throw 'Existing signing fingerprint differs. Refusing to replace production key.'
}
$secretNames = @('ANDROIDOS_SIGNING_KEYSTORE_B64','ANDROIDOS_SIGNING_STORE_PASSWORD','ANDROIDOS_SIGNING_KEY_PASSWORD','ANDROIDOS_SIGNING_KEY_ALIAS')
$present = @(& gh secret list -e $Environment -R $Repository --json name | ConvertFrom-Json | ForEach-Object { $_.name })
Assert-Last 'Inspect existing protected secrets'
if (@($present | Where-Object { $_ -in $secretNames }).Count -gt 0 -and @($present | Where-Object { $_ -in $secretNames }).Count -ne 4) {
    throw 'Partial GitHub signing secrets found. Refusing to overwrite; inspect manually.'
}
# Piping to gh secret set hides the payload from process arguments / shell history.
[Convert]::ToBase64String([IO.File]::ReadAllBytes($keyFile)) | & gh secret set ANDROIDOS_SIGNING_KEYSTORE_B64 -e $Environment -R $Repository
Assert-Last 'Upload encrypted keystore secret'
$password | & gh secret set ANDROIDOS_SIGNING_STORE_PASSWORD -e $Environment -R $Repository
Assert-Last 'Upload store password secret'
$password | & gh secret set ANDROIDOS_SIGNING_KEY_PASSWORD -e $Environment -R $Repository
Assert-Last 'Upload key password secret'
$alias | & gh secret set ANDROIDOS_SIGNING_KEY_ALIAS -e $Environment -R $Repository
Assert-Last 'Upload key alias secret'
& gh variable set ANDROIDOS_CERT_SHA256 -e $Environment -R $Repository --body $fingerprint
Assert-Last 'Pin signing certificate'
$available = @(& gh secret list -e $Environment -R $Repository --json name | ConvertFrom-Json | ForEach-Object { $_.name })
Assert-Last 'Verify GitHub signing secret names'
foreach ($name in $secretNames) { if ($name -notin $available) { throw "Missing secret: $name" } }
Write-Host 'CONFIGURED: 4 GitHub Environment Secrets + 1 certificate variable.'
Write-Host "Signing certificate SHA-256: $fingerprint"
Write-Host "Local key path: $keyFile"
Write-Host 'IMPORTANT: The local password.dpapi can be decrypted only by this Windows user profile.'
Write-Host 'Make a secure, independent OFFLINE backup of the key and recovery password; never commit these files.'
