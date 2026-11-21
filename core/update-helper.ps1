# Fixed, bundled transaction helper. No URLs, commands or user-data paths from manifest.
param([Parameter(Mandatory=$true)][string]$Plan, [switch]$Recover)
$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$p = Get-Content -LiteralPath $Plan -Raw -Encoding UTF8 | ConvertFrom-Json
$root = [IO.Path]::GetFullPath($p.root)
$tx = [IO.Path]::GetFullPath((Split-Path -Parent $Plan))
if ((Split-Path -Parent (Split-Path -Parent $tx)) -ne $root) { throw 'Invalid transaction root' }
$exe = Join-Path $root 'bili-danmaku-song-order.exe'
$backup = Join-Path $root 'backup'
$stage = Join-Path $tx 'staged'
$old = Join-Path $tx 'previous-current'
$older = Join-Path $tx 'previous-backup'
$files = @('bili-danmaku-song-order.exe','LICENSE','THIRD_PARTY_NOTICES.md')
$replaced = $false
function Safe([string]$Path) {
 $item = $Path
 while ($item) {
  if (Test-Path -LiteralPath $item) {
   if ((Get-Item -Force -LiteralPath $item).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse path rejected' }
  }
  $next = Split-Path -Parent $item
  if ($next -eq $item) { break }; $item = $next
 }
}
function Save-State([string]$Phase, [string]$Message) {
 $record = @{phase=$Phase;message=$Message;version=$p.version;token=$p.token}
 $temp = Join-Path $tx 'state.tmp'
 [IO.File]::WriteAllText($temp,($record | ConvertTo-Json),$utf8)
 Move-Item -LiteralPath $temp -Destination (Join-Path $tx 'state.json') -Force
}
function Wait-FileFree {
 for ($i=0;$i -lt 120;$i++) {
  try { $s=[IO.File]::Open($exe,'Open','ReadWrite','None');$s.Dispose();return } catch { Start-Sleep -Milliseconds 500 }
 }
 throw 'Executable is busy. Close other copies before retrying.'
}
function Hash([string]$File) { return (Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLowerInvariant() }
function Restore-Current {
 foreach($name in $files) {
  $saved = Join-Path $old $name
  if(Test-Path -LiteralPath $saved) { Move-Item -LiteralPath $saved -Destination (Join-Path $root $name) -Force }
  elseif($p.originalFiles -notcontains $name) { Remove-Item -LiteralPath (Join-Path $root $name) -Force -ErrorAction SilentlyContinue }
 }
 if(Test-Path -LiteralPath $older) {
  if(Test-Path -LiteralPath $backup){Remove-Item -LiteralPath $backup -Recurse -Force}
  Move-Item -LiteralPath $older -Destination $backup
 }
}
try {
 Safe $root; Safe $tx; Safe $backup
 if([IO.Path]::GetFileName($tx) -ne $p.token -or $p.token -notmatch '^[0-9a-f]{32}$') {throw 'Invalid transaction token'}
 [IO.File]::WriteAllText((Join-Path $tx 'helper-ready'),'ready',$utf8)
 $go=$false
 for($i=0;$i -lt 150;$i++){
  if(Test-Path -LiteralPath (Join-Path $tx 'install-go')){$go=$true;break}
  Start-Sleep -Milliseconds 100
 }
 if(-not $go){throw 'Application did not authorize installation; nothing replaced'}
 if($Recover) {
  $process=Get-Process -Id $p.pid -ErrorAction SilentlyContinue
  if($process -and -not $process.WaitForExit(60000)){throw 'Close the application before recovery'}
  if(Test-Path -LiteralPath $exe){Wait-FileFree}
  Safe $old;Safe $older
  foreach($name in $p.originalFiles){
   $saved=Join-Path $old $name
   $candidate=if(Test-Path -LiteralPath $saved){$saved}else{Join-Path $root $name}
   Safe $candidate
   if((Hash $candidate) -ne $p.originalHashes.PSObject.Properties[$name].Value){throw 'Recovery backup verification failed'}
  }
  Restore-Current
  Save-State 'restored' 'Previous application restored after interrupted update'
  $arguments=@();if($p.testMode){$arguments+=@('--release-smoke-test')}
  if($arguments.Count){Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $root}else{Start-Process -FilePath $exe -WorkingDirectory $root}
  exit 0
 }
 if($p.action -notin @('upgrade','rollback')) {throw 'Invalid action'}
 foreach($name in $files) {
  $file=Join-Path $stage $name;Safe $file
  $expected=$p.files.PSObject.Properties[$name].Value
  if($expected -notmatch '^[0-9a-f]{64}$' -or (Hash $file) -ne $expected) {throw "Invalid staged file: $name"}
 }
 # Wait only for the recorded process, then also check the executable file lock.
 $process=Get-Process -Id $p.pid -ErrorAction SilentlyContinue
 if($process) { if(-not $process.WaitForExit(60000)) {throw 'Application did not exit; nothing replaced'} }
 Wait-FileFree
 if((Hash $exe) -ne $p.currentHash) {throw 'Current executable changed; installation cancelled'}
 New-Item -ItemType Directory -Path $old -Force | Out-Null
 if(Test-Path -LiteralPath $backup){Move-Item -LiteralPath $backup -Destination $older}
 Save-State 'replacing' 'Replacing application files'
 $replaced = $true
 foreach($name in $files) {
  $target=Join-Path $root $name
  if(Test-Path -LiteralPath $target){Move-Item -LiteralPath $target -Destination (Join-Path $old $name)}
  Move-Item -LiteralPath (Join-Path $stage $name) -Destination $target
 }
 Save-State 'starting' 'Waiting for the new GUI and Python bridge'
 $arguments=@('--update-health', $p.token)
 if($p.testMode){$arguments+=@('--release-smoke-test')}
 $new=Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $root -PassThru
 $healthy=$false
 for($i=0;$i -lt 180;$i++) {
  $ack=Join-Path $tx 'healthy.json'
  if(Test-Path -LiteralPath $ack){
   $a=Get-Content -LiteralPath $ack -Raw -Encoding UTF8 | ConvertFrom-Json
   if($a.token -eq $p.token -and $a.version -eq $p.version -and (Hash $exe) -eq $p.files.'bili-danmaku-song-order.exe') {$healthy=$true;break}
  }
  if($new.HasExited){break};Start-Sleep -Milliseconds 500;$new.Refresh()
 }
 if(-not $healthy){
  if(-not $new.HasExited){
   # Do not kill a possibly working GUI or overwrite its locked EXE.
   Save-State 'needs-attention' 'Startup confirmation timed out. Close the new application before recovery.'
   exit 2
  }
  Wait-FileFree;Restore-Current
  Save-State 'restored' 'New application failed startup; previous version restored'
  $args=@();if($p.testMode){$args+=@('--release-smoke-test')}
  if($args.Count){Start-Process -FilePath $exe -ArgumentList $args -WorkingDirectory $root}else{Start-Process -FilePath $exe -WorkingDirectory $root}
  exit 1
 }
 Move-Item -LiteralPath $old -Destination $backup
 $meta=@{version=$p.currentVersion;files=$p.originalHashes;installedVersion=$p.version}
 [IO.File]::WriteAllText((Join-Path $backup 'version.json'),($meta|ConvertTo-Json -Depth 5),$utf8)
 if($p.action -eq 'rollback') {
  [IO.File]::WriteAllText((Join-Path (Split-Path -Parent $tx) 'skip-version.json'),(@{version=$p.currentVersion}|ConvertTo-Json),$utf8)
 }
 if(Test-Path -LiteralPath $older){Remove-Item -LiteralPath $older -Recurse -Force}
 Save-State 'complete' 'Application startup confirmed'
 Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
 Remove-Item -LiteralPath (Join-Path $tx 'package.zip') -Force -ErrorAction SilentlyContinue
} catch {
 $message=$_.Exception.Message
 try {
  if($replaced -and -not (Test-Path -LiteralPath $old)) {
   Save-State 'needs-attention' ('New GUI started, but backup finalization failed: '+$message)
  } else {
   if($replaced -and (Test-Path -LiteralPath $old)){if(Test-Path -LiteralPath $exe){Wait-FileFree};Restore-Current}
   elseif(Test-Path -LiteralPath $older){Move-Item -LiteralPath $older -Destination $backup}
   Save-State 'failed' $message
  }
 } catch { Save-State 'needs-attention' ($message+'; recovery: '+$_.Exception.Message) }
 exit 1
}
