param(
    [Parameter(Mandatory = $false)]
    [string]$Message = "",

    [Parameter(Mandatory = $false)]
    [string]$Port = "COM4",

    [Parameter(Mandatory = $false)]
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8

$interactive = [string]::IsNullOrWhiteSpace($Message)

$serial = New-Object System.IO.Ports.SerialPort(
    $Port,
    115200,
    [System.IO.Ports.Parity]::None,
    8,
    [System.IO.Ports.StopBits]::One
)
$serial.Encoding = $utf8
$serial.ReadTimeout = 200
$serial.WriteTimeout = 2000
$serial.DtrEnable = $false
$serial.RtsEnable = $false

try {
    Write-Host "Opening $Port ..."
    $serial.Open()
    $serial.DiscardInBuffer()

    function Wait-DevicePrompt([bool]$RequireAudioResult) {
        $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
        $buffer = ""
        $sawAudioResult = -not $RequireAudioResult

        while ([DateTime]::UtcNow -lt $deadline) {
            Start-Sleep -Milliseconds 50
            $chunk = $serial.ReadExisting()
            if ([string]::IsNullOrEmpty($chunk)) {
                continue
            }

            Write-Host -NoNewline $chunk
            $buffer += $chunk
            if ($buffer.Length -gt 16384) {
                $buffer = $buffer.Substring($buffer.Length - 16384)
            }

            if ($buffer.Contains("RLCD42_AUDIO_RESULT:FAIL")) {
                throw "The device reported an audio error."
            }
            if ($buffer.Contains("RLCD42_AUDIO_RESULT:OK PA=LOW")) {
                $sawAudioResult = $true
            }

            # Keep this source file ASCII-only so Windows PowerShell 5.1 does
            # not misdecode a UTF-8 prompt literal. The prompt ends in "> ".
            if ($sawAudioResult -and $buffer.EndsWith("> ")) {
                return
            }
        }
        throw "Timed out waiting for RLCD4.2. Check $Port and reconnect USB."
    }

    # A blank line asks an already-running console to print a fresh prompt.
    $serial.Write("`r`n")
    Wait-DevicePrompt $false

    while ($true) {
        if ($interactive) {
            $nextMessage = Read-Host "Message (blank line exits)"
            if ([string]::IsNullOrWhiteSpace($nextMessage)) {
                Write-Host "Done."
                break
            }
        }
        else {
            $nextMessage = $Message
        }

        if ($nextMessage.StartsWith("!")) {
            Write-Host "Do not add the leading !; it is added automatically."
            if ($interactive) { continue } else { throw "Invalid message." }
        }
        if ($nextMessage.Contains("`r") -or $nextMessage.Contains("`n")) {
            Write-Host "Message must be one line."
            if ($interactive) { continue } else { throw "Invalid message." }
        }

        Write-Host "Sending: $nextMessage"
        $serial.Write("!" + $nextMessage + "`r`n")
        Wait-DevicePrompt $true
        Write-Host ""
        Write-Host "OK: speech playback finished."

        if (-not $interactive) {
            break
        }
    }
}
finally {
    if ($serial.IsOpen) {
        $serial.Close()
    }
    $serial.Dispose()
}
