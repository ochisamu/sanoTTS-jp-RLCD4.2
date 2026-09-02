#!/usr/bin/env python3
"""Safe host-side bring-up tool for the Waveshare RLCD 4.2 sanoTTS demo.

The tool intentionally has no erase-flash/eFuse command. A matching, twice-read
16 MiB factory backup is required before custom firmware can be flashed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parents[1]
FIRMWARE = ROOT / "firmware"
ASSETS = ROOT / "assets"
DIST = ROOT / "dist"
FLASH_BYTES = 16 * 1024 * 1024
MIN_DIRAM_REMAIN = 8 * 1024
UPSTREAM_COMMIT = "8f76437fe82604b3d77dc6a5ddbd0e4f557a750d"
BOARD_ID = "ESP32-S3-RLCD-4.2"
BOARD_NAME = "Waveshare ESP32-S3-RLCD-4.2"
MANIFEST_SCHEMA = 3
PROFILES = ("probe", "kana", "kanji")
APP_OFFSET = 0x10000
APP_PARTITION_BYTES = 0x200000
PROFILE_MARKERS = {
    "probe": b"RLCD42_PROFILE:probe",
    "kana": b"RLCD42_PROFILE:kana-audio",
    "kana-silent": b"RLCD42_PROFILE:kana-silent",
    "kanji": b"RLCD42_PROFILE:kanji-audio",
    "kanji-silent": b"RLCD42_PROFILE:kanji-silent",
}
CAPABILITY_MARKERS = {
    "battery": b"RLCD42_CAP:battery-adc1-ch3-x3-v1",
    "key": b"RLCD42_CAP:key-local-demo-v1",
}
FACTORY_MARKERS = (
    b"S3_RLCD_4_2",
    b"waveshare-s3-rlcd-4.2",
    b"ESP32-S3-RLCD-4.2",
)
DEMO_KANA = "きょ][おわよ][いて][んきです°ね"
DEMO_KANJI = "!今日は良い天気ですね。"


def default_backup_dir() -> pathlib.Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return pathlib.Path(os.environ["LOCALAPPDATA"]) / "RLCD42SanoTTSDemo" / "backups"
    data_home = os.environ.get("XDG_DATA_HOME")
    base = pathlib.Path(data_home).expanduser() if data_home else pathlib.Path.home() / ".local" / "share"
    return base / "rlcd42-sanotts-demo" / "backups"


# Factory images can contain Wi-Fi credentials or device tokens. Keep them
# outside the repository (and usually outside cloud-synced workspace folders).
BACKUPS = default_backup_dir()

ASSET_SPECS = {
    "model": {
        "name": "saanotts-jp-v3-int8.bin",
        "url": "https://github.com/ayutaz/sanoTTS-jp/releases/download/v0.2.0/saanotts-jp-v3-int8.bin",
        "size": 643_936,
        "sha256": "c3b89216133fa7bee3f61ed9d8e6c7183a5dfd41b70dab194f42c20fce5b4170",
    },
    "dict": {
        "name": "k1-dict-438750.bin",
        "url": "https://github.com/ayutaz/sanoTTS-jp/releases/download/v0.2.0/k1-dict-438750.bin",
        "size": 13_702_320,
        "sha256": "f162c922074d76817298b34d8a8fd35f7d195f38540303485a76c956b5d84877",
    },
}

DIST_NOTICE_FILES = {
    ROOT / "LICENSE": "LICENSE-MIT.txt",
    ROOT / "NOTICE.md": "NOTICE.md",
    ROOT / "licenses/sanoTTS-jp-model.md": "LICENSE-MODEL.md",
    ROOT / "licenses/sanoTTS-jp-model-card.md": "MODEL_CARD.md",
    ROOT / "licenses/waveshare-examples-Apache-2.0.txt": "LICENSE-WAVESHARE-APACHE-2.0.txt",
    ROOT / "licenses/NOTICE-openjtalk.txt": "NOTICE-openjtalk.txt",
    ROOT / "licenses/NOTICE-dictionary.txt": "NOTICE-dictionary.txt",
    ROOT / "licenses/openjtalk-PROVENANCE.md": "openjtalk-PROVENANCE.md",
}


class DemoError(RuntimeError):
    pass


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def print_command(command: list[str], cwd: pathlib.Path | None = None) -> None:
    rendered = " ".join(subprocess.list2cmdline([part]) for part in command)
    prefix = f"[{cwd}] " if cwd else ""
    print(f"+ {prefix}{rendered}", flush=True)


def run(
    command: list[str],
    *,
    cwd: pathlib.Path | None = None,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    print_command(command, cwd)
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        check=False,
    )
    if capture and result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if check and result.returncode != 0:
        raise DemoError(f"command failed with exit code {result.returncode}")
    return result


def executable(name: str) -> str | None:
    return shutil.which(name)


def esptool_command() -> list[str]:
    configured = os.environ.get("ESPTOOL")
    if configured:
        return [configured]
    for name in ("esptool.py", "esptool"):
        found = executable(name)
        if found:
            return [found]
    if importlib.util.find_spec("esptool") is not None:
        return [sys.executable, "-m", "esptool"]
    raise DemoError(
        "esptool was not found. Activate ESP-IDF first (source export.sh), "
        "or install esptool in this Python environment."
    )


def idf_command() -> str:
    found = executable("idf.py")
    if not found:
        raise DemoError("idf.py was not found. Activate ESP-IDF v5.5.x first (source export.sh).")
    return found


def esptool(port: str, operation: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return run(
        esptool_command() + ["--chip", "esp32s3", "--port", port] + operation,
        capture=capture,
    )


def parse_mac(output: str) -> str:
    match = re.search(r"\bMAC:\s*([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})\b", output)
    if not match:
        match = re.search(r"\b([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})\b", output)
    if not match:
        raise DemoError("could not read the device MAC address from esptool output")
    return match.group(1).lower()


def read_mac(port: str) -> str:
    return parse_mac(esptool(port, ["read_mac"], capture=True).stdout or "")


def security_is_enabled(output: str) -> bool:
    lowered = output.lower()
    enabled_patterns = (
        r"secure\s+boot[^\n]*enabled",
        r"flash\s+encryption[^\n]*enabled",
        r"secure_boot_en\s*=\s*true",
        r"flash_crypt_cnt[^\n]*(?:odd|enabled)",
    )
    return any(re.search(pattern, lowered) for pattern in enabled_patterns)


def normalized_security(output: str) -> dict[str, str]:
    """Return explicit, stable states from version-dependent esptool text."""
    def state(pattern: str) -> str:
        match = re.search(pattern + r"[^\n]*\b(enabled|disabled)\b", output, re.I)
        return match.group(1).lower() if match else "unknown"

    secure_boot = state(r"secure[ _-]*boot")
    flash_encryption = state(r"flash[ _-]*encryption")
    if flash_encryption == "unknown" and re.search(
        r"flash_crypt_cnt[^\n]*(?:odd|enabled)", output, re.I
    ):
        flash_encryption = "enabled"
    return {"secure_boot": secure_boot, "flash_encryption": flash_encryption}


def require_unsecured_state(state: dict[str, str]) -> None:
    if state.get("secure_boot") != "disabled" or state.get("flash_encryption") != "disabled":
        raise DemoError(
            "secure-boot/flash-encryption state is enabled or could not be proven disabled; "
            "refusing this write operation"
        )


def require_board_confirmation(value: str | None) -> dict[str, str]:
    if value != BOARD_ID:
        raise DemoError(
            f"read the physical board silkscreen and pass --confirm-board {BOARD_ID}; "
            "ESP32-S3/16 MB/USB identifiers alone do not prove the board model"
        )
    return {"method": "typed-silkscreen", "value": BOARD_ID}


def inspect_device(port: str, *, require_unsecured: bool = False) -> dict[str, object]:
    chip = esptool(port, ["chip_id"], capture=True).stdout or ""
    if "ESP32-S3" not in chip.upper().replace(" ", ""):
        # Older esptool writes "ESP32-S3" normally. Keep a strict guard here:
        # selecting the wrong target is more costly than asking the user to update esptool.
        raise DemoError("the connected chip was not identified as ESP32-S3")
    flash = esptool(port, ["flash_id"], capture=True).stdout or ""
    if not re.search(r"(?:detected\s+flash\s+size|flash\s+size)\s*:\s*16\s*MB", flash, re.I):
        raise DemoError("the connected device was not reported as a 16 MB flash device")
    security = esptool(port, ["get_security_info"], capture=True).stdout or ""
    mac_output = esptool(port, ["read_mac"], capture=True).stdout or ""
    state = normalized_security(security)
    if require_unsecured:
        require_unsecured_state(state)
    return {
        "chip": chip,
        "flash": flash,
        "security": security,
        "security_state": state,
        "mac": parse_mac(mac_output),
    }


def find_factory_markers(image: pathlib.Path) -> list[dict[str, object]]:
    data = image.read_bytes()
    found: list[dict[str, object]] = []
    for marker in FACTORY_MARKERS:
        offset = data.find(marker)
        if offset >= 0:
            found.append({"text": marker.decode("ascii"), "offset": offset})
    return found


def parse_installed_profile(data: bytes) -> str:
    found = [name for name, marker in PROFILE_MARKERS.items() if marker in data]
    if len(found) != 1:
        detail = "none" if not found else ", ".join(found)
        raise DemoError(
            f"could not prove one installed RLCD demo profile (found: {detail}); "
            "flash the intended profile before sending an utterance"
        )
    return found[0]


def verify_built_capabilities(image: pathlib.Path, profile: str) -> None:
    data = image.read_bytes()
    installed = parse_installed_profile(data)
    if installed != profile:
        raise DemoError(
            f"built image marker is {installed}, expected {profile}"
        )
    required = ("battery",) if profile == "probe" else ("battery", "key")
    missing = [name for name in required if CAPABILITY_MARKERS[name] not in data]
    if missing:
        raise DemoError(
            "built image is missing required capability marker(s): " + ", ".join(missing)
        )
    print("OK  capabilities: " + ", ".join(required))


def detect_installed_profile(port: str) -> str:
    with tempfile.TemporaryDirectory(prefix="rlcd42-profile-") as temporary:
        image = pathlib.Path(temporary) / "app-partition.bin"
        esptool(port, [
            "read_flash", "--no-progress", hex(APP_OFFSET),
            hex(APP_PARTITION_BYTES), str(image),
        ])
        if image.stat().st_size != APP_PARTITION_BYTES:
            raise DemoError("installed app-partition read has the wrong size")
        return parse_installed_profile(image.read_bytes())


def verify_asset(spec: dict[str, object], path: pathlib.Path) -> None:
    size = path.stat().st_size
    if size != spec["size"]:
        raise DemoError(f"{path.name}: size {size} does not match expected {spec['size']}")
    actual = sha256_file(path)
    if actual != spec["sha256"]:
        raise DemoError(f"{path.name}: SHA-256 mismatch ({actual})")


def download_asset(spec: dict[str, object]) -> pathlib.Path:
    ASSETS.mkdir(parents=True, exist_ok=True)
    destination = ASSETS / str(spec["name"])
    if destination.exists():
        verify_asset(spec, destination)
        print(f"OK  {destination.relative_to(ROOT)} (already verified)")
        return destination

    print(f"GET {spec['url']}")
    with tempfile.NamedTemporaryFile(prefix=f".{destination.name}.", dir=ASSETS, delete=False) as temp:
        temp_path = pathlib.Path(temp.name)
        try:
            request = urllib.request.Request(str(spec["url"]), headers={"User-Agent": "rlcd42-sanotts-demo/0.1"})
            with urllib.request.urlopen(request, timeout=60) as response:
                shutil.copyfileobj(response, temp, length=1024 * 1024)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
    try:
        verify_asset(spec, temp_path)
        temp_path.replace(destination)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    print(f"OK  {destination.relative_to(ROOT)}  sha256={spec['sha256']}")
    return destination


def cmd_fetch(args: argparse.Namespace) -> None:
    if not args.accept_model_license:
        raise DemoError(
            "read licenses/sanoTTS-jp-model.md and rerun with --accept-model-license; "
            "the model and generated audio are not MIT licensed"
        )
    download_asset(ASSET_SPECS["model"])
    if args.kanji:
        download_asset(ASSET_SPECS["dict"])


def cmd_check(_: argparse.Namespace) -> None:
    required = [
        ROOT / ".gitmodules",
        ROOT / "NOTICE.md",
        ROOT / "licenses/sanoTTS-jp-model.md",
        ROOT / "licenses/sanoTTS-jp-model-card.md",
        ROOT / "licenses/waveshare-examples-Apache-2.0.txt",
        FIRMWARE / "main/saan_memory.lf",
        FIRMWARE / "main/rlcd42_entry.c",
        FIRMWARE / "main/rlcd42_probe.c",
        FIRMWARE / "main/rlcd42_saan_i2s.c",
        FIRMWARE / "main/rlcd42_board.c",
        FIRMWARE / "main/rlcd42_battery.c",
        FIRMWARE / "main/rlcd42_battery.h",
        FIRMWARE / "main/rlcd42_console.c",
        FIRMWARE / "main/rlcd42_display.c",
    ] + list(DIST_NOTICE_FILES)
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise DemoError("missing repository files: " + ", ".join(missing))
    upstream = ROOT / "third_party/sanoTTS-jp"
    result = run(["git", "rev-parse", "HEAD"], cwd=upstream, capture=True)
    revision = (result.stdout or "").strip().splitlines()[-1]
    if revision != UPSTREAM_COMMIT:
        raise DemoError(f"unexpected sanoTTS revision {revision}; expected {UPSTREAM_COMMIT}")
    audio_source = (FIRMWARE / "main/rlcd42_saan_i2s.c").read_text(encoding="utf-8")
    entry_source = (FIRMWARE / "main/rlcd42_entry.c").read_text(encoding="utf-8")
    probe_source = (FIRMWARE / "main/rlcd42_probe.c").read_text(encoding="utf-8")
    board_source = (FIRMWARE / "main/rlcd42_board.c").read_text(encoding="utf-8")
    battery_source = (FIRMWARE / "main/rlcd42_battery.c").read_text(encoding="utf-8")
    console_source = (FIRMWARE / "main/rlcd42_console.c").read_text(encoding="utf-8")
    display_source = (FIRMWARE / "main/rlcd42_display.c").read_text(encoding="utf-8")
    cmake_source = (FIRMWARE / "main/CMakeLists.txt").read_text(encoding="utf-8")
    memory_layout = (FIRMWARE / "main/saan_memory.lf").read_text(encoding="utf-8")
    sdkconfig = (FIRMWARE / "sdkconfig.defaults").read_text(encoding="utf-8")
    notice = (ROOT / "NOTICE.md").read_text(encoding="utf-8")
    expected_tokens = {
        "audio": (audio_source, (
            "RLCD42_I2S_MCLK GPIO_NUM_16", "RLCD42_I2S_BCLK GPIO_NUM_9",
            "RLCD42_I2S_WS   GPIO_NUM_45", "RLCD42_I2S_DOUT GPIO_NUM_8",
            "RLCD42_I2S_DIN  GPIO_NUM_10", "AUDIO_VOLUME       100",
            "write_mono_chunks(s_preroll, s_preroll_fill)",
            "esp_codec_dev_set_out_vol(s_output, 0) != ESP_CODEC_DEV_OK",
            "ES8311_VOLUME_ZERO    0x00",
            "codec_volume_is(ES8311_VOLUME_ZERO, \"zero-volume-before-PA\")",
            "codec_mute_is(true, \"mute-before-PA\")",
            "codec_volume_is((uint8_t)(0x56 + volume), \"volume-ramp\")",
            "i2s_channel_enable(s_tx)",
            "ES8311 MCLK primed before codec reset/config; PA remains LOW",
            "RLCD42_AUDIO_RESULT:OK PA=LOW",
            "rlcd42_saan_stream_pull",
        )),
        "entry": (entry_source, (
            "RLCD42_PROFILE:", "rlcd42_board_init()", "saan_upstream_app_main()",
        )),
        "probe": (probe_source, (
            "EXPECTED_FLASH_BYTES", "EXPECTED_PSRAM_BYTES", "{0x18, \"ES8311\"}",
            "{0x40, \"ES7210\"}", "{0x51, \"PCF85063\"}", "{0x70, \"SHTC3\"}",
        )),
        "board": (board_source, (
            "RLCD42_I2C_SDA  GPIO_NUM_13", "RLCD42_I2C_SCL  GPIO_NUM_14",
            "RLCD42_PA_EN     GPIO_NUM_46", "force_amp_low_first",
        )),
        "battery": (battery_source, (
            "RLCD42_BATTERY_ADC_UNIT    ADC_UNIT_1",
            "RLCD42_BATTERY_ADC_CHANNEL ADC_CHANNEL_3",
            "RLCD42_BATTERY_ADC_GPIO    GPIO_NUM_4",
            "RLCD42_BATTERY_DIVIDER     3u",
            "RLCD42_BATTERY_SAMPLES     16u",
            "ADC_ATTEN_DB_12", "ADC_BITWIDTH_12",
            "adc_oneshot_io_to_channel",
            "adc_cali_create_scheme_curve_fitting",
            "RLCD42_CAP:battery-adc1-ch3-x3-v1",
        )),
        "console": (console_source, (
            "RLCD42_KEY_GPIO       GPIO_NUM_18",
            "KEY_DEBOUNCE_SAMPLES  3",
            "pdMS_TO_TICKS(KEY_POLL_MS)",
            "pdMS_TO_TICKS(5)",
            "s_key_seen_released = s_key_stable != 0",
            "!s_line.done &&",
            "*out = SAAN_DEMO_INTERMEDIATE",
            "RLCD42_CAP:key-local-demo-v1",
        )),
        "display": (display_source, (
            "RLCD_PIN_DC      GPIO_NUM_5", "RLCD_PIN_CS      GPIO_NUM_40",
            "RLCD_PIN_SCLK    GPIO_NUM_11", "RLCD_PIN_MOSI    GPIO_NUM_12",
            "RLCD_PIN_RESET   GPIO_NUM_41", "RLCD_SPI_HZ      (10 * 1000 * 1000)",
            "RLCD_FB_BYTES == 15000", "EXT_RAM_BSS_ATTR static uint8_t s_framebuffer",
        )),
        "memory": (memory_layout, (
            "main:g_ids (saan_token_ids_ext)", "bss -> extern_ram",
        )),
        "notice": (notice, (
            "This model was distilled from a piper-plus teacher model.",
            "つくよみちゃんコーパス", "Pinned reference revision: `eb1f6342",
        )),
    }
    for section, (source, tokens) in expected_tokens.items():
        absent = [token for token in tokens if token not in source]
        if absent:
            raise DemoError(f"{section} safety constants changed or disappeared: " + ", ".join(absent))
    if "portMAX_DELAY" in console_source:
        raise DemoError("local KEY console must not block forever when no USB host is attached")
    if cmake_source.count('"rlcd42_battery.c"') != 2 or cmake_source.count("esp_adc") < 2:
        raise DemoError("probe and TTS builds must both include calibrated battery telemetry")
    if '"rlcd42_console.c"' not in cmake_source or '"${SAAN_MAIN}/saan_console.c"' in cmake_source:
        raise DemoError("TTS builds must use the RLCD4.2 USB/KEY console adapter")
    if "saan_stream_pull=rlcd42_saan_stream_pull" not in cmake_source:
        raise DemoError("upstream stream failures must propagate into the verified result marker")
    if "SAAN_I2S_PREROLL_SAMPLES=262144" not in cmake_source:
        raise DemoError("RLCD4.2 must buffer short utterances before playback")
    if "CONFIG_SPIRAM_MODE_OCT=y" not in sdkconfig or "CONFIG_SPIRAM_MODE_QUAD=y" in sdkconfig:
        raise DemoError("RLCD4.2 requires 8 MB Octal PSRAM configuration")
    if "CONFIG_SPIRAM_ALLOW_BSS_SEG_EXTERNAL_MEMORY=y" not in sdkconfig:
        raise DemoError("RLCD4.2 framebuffer and token-ID buffer require external BSS support")
    if "CONFIG_CODEC_ES8311_SUPPORT=y" not in sdkconfig or "CONFIG_CODEC_AW88298_SUPPORT=y" in sdkconfig:
        raise DemoError("only the RLCD4.2 ES8311 output codec may be enabled")
    if ("CONFIG_ESP_BROWNOUT_DET=y" not in sdkconfig or
            "CONFIG_ESP_BROWNOUT_DET_LVL_SEL_7=y" not in sdkconfig):
        raise DemoError("ESP32-S3 hardware brownout protection must stay explicitly enabled")
    print("OK  pinned sanoTTS revision")
    print("OK  RLCD4.2 LCD, I2C, I2S, PA and Octal-PSRAM constants")
    print("OK  model license and attribution notice are present")


def cmd_doctor(args: argparse.Namespace) -> None:
    require_board_confirmation(args.confirm_board)
    cmd_check(args)
    if not executable("idf.py"):
        print("WARN idf.py is not active; build/flash commands will need ESP-IDF v5.5.x")
    info = inspect_device(args.port)
    print(f"OK  ESP32-S3 / 16 MB / MAC {info['mac']}")
    print(f"OK  typed physical-board confirmation: {BOARD_ID}")
    state = info["security_state"]
    if not isinstance(state, dict) or any(value != "disabled" for value in state.values()):
        print("WARN security state is enabled or not explicit; custom writes are blocked")
    else:
        print("OK  no enabled secure-boot/flash-encryption flag was reported")
    print("NOTE chip/flash/USB identifiers are compatible but do not prove the PCB model by themselves")


def cmd_backup(args: argparse.Namespace) -> None:
    confirmation = require_board_confirmation(args.confirm_board)
    info = inspect_device(args.port)
    BACKUPS.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        BACKUPS.chmod(0o700)
    except OSError:
        pass
    stamp = dt.datetime.now().astimezone().strftime("%Y%m%dT%H%M%S-%f%z")
    mac = str(info["mac"])
    stem = f"rlcd42-backup-{stamp}-{mac.replace(':', '')}"
    final_image = BACKUPS / f"{stem}.bin"
    manifest_path = BACKUPS / f"{stem}.json"
    with tempfile.TemporaryDirectory(prefix="rlcd42-backup-") as temporary:
        temp_dir = pathlib.Path(temporary)
        images = [temp_dir / "read-1.bin", temp_dir / "read-2.bin"]
        hashes: list[str] = []
        for index, image in enumerate(images, start=1):
            print(f"Reading full 16 MiB flash ({index}/2). Do not disconnect USB.")
            esptool(args.port, ["read_flash", "--no-progress", "0x0", hex(FLASH_BYTES), str(image)])
            if image.stat().st_size != FLASH_BYTES:
                raise DemoError(f"backup read {index} has the wrong size")
            hashes.append(sha256_file(image))
        if hashes[0] != hashes[1]:
            raise DemoError("the two full-flash reads differ; no backup was accepted")
        final_info = inspect_device(args.port)
        if final_info["mac"] != info["mac"]:
            raise DemoError(
                f"device MAC changed during backup ({info['mac']} -> {final_info['mac']}); "
                "no backup was accepted"
            )
        markers = find_factory_markers(images[0])
        role = "snapshot" if has_recovery_baseline(mac, info["security_state"]) else "recovery-baseline"
        if final_image.exists() or manifest_path.exists():
            raise DemoError("backup destination already exists; refusing to overwrite it")
        shutil.copyfile(images[0], final_image)

    try:
        final_image.chmod(0o600)
    except OSError:
        pass

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "device": BOARD_NAME,
        "board": BOARD_ID,
        "board_confirmation": confirmation,
        "chip": "ESP32-S3",
        "flash_bytes": FLASH_BYTES,
        "mac": info["mac"],
        "security": info["security_state"],
        "security_output_sha256": hashlib.sha256(str(info["security"]).encode("utf-8")).hexdigest(),
        "flash_probe_sha256": hashlib.sha256(str(info["flash"]).encode("utf-8")).hexdigest(),
        "port_at_backup": args.port,
        "image": final_image.name,
        "sha256": hashes[0],
        "reads": 2,
        "role": role,
        "factory_markers": markers,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        manifest_path.chmod(0o600)
    except OSError:
        pass
    print(f"OK  {final_image}")
    print(f"OK  two identical reads, sha256={hashes[0]}")
    print(f"OK  backup role: {role}")
    if markers:
        labels = ", ".join(f"{item['text']}@0x{int(item['offset']):x}" for item in markers)
        print(f"OK  factory board marker(s): {labels}")
    else:
        print("WARN no known factory marker was found; typed silkscreen confirmation is recorded")
    print("Keep this backup private: it can contain Wi-Fi/account/device settings.")


def build_parameters(profile: str, silent: bool = False) -> tuple[str, pathlib.Path, list[str]]:
    if profile not in PROFILES:
        raise DemoError(f"unknown profile {profile!r}")
    if profile == "probe" and silent:
        raise DemoError("probe already contains no model or audio path; do not add --silent")
    build_name = profile + ("-silent" if silent else "")
    build_dir = FIRMWARE / f"build-{build_name}"
    # Each profile needs its own sdkconfig. Sharing firmware/sdkconfig makes a
    # prior kana build silently override the kanji partition table (and vice
    # versa), which is unsafe for a full-flash image.
    definitions = [f"-DSDKCONFIG={build_dir / 'sdkconfig'}"]
    if profile == "probe":
        definitions.append("-DSAAN_BOARD_PROBE=1")
    else:
        definitions.append("-DSAAN_ENABLE_PIE=1")
    if silent:
        definitions.append("-DSAAN_SILENT=1")
    if profile == "kanji":
        definitions += ["-DSAAN_KANJI=1", "-DSDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.kanji"]
    return build_name, build_dir, definitions


def check_build_margin(profile: str, build_dir: pathlib.Path) -> None:
    map_file = build_dir / "rlcd42_sanotts_demo.map"
    if not map_file.is_file():
        raise DemoError(f"build map is missing: {map_file}")
    result = subprocess.run(
        [sys.executable, "-m", "esp_idf_size", "--format", "json", str(map_file)],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise DemoError("esp-idf-size could not inspect the linked firmware: " + result.stderr.strip())
    try:
        size = json.loads(result.stdout)
        remaining = int(size["diram_remain"])
        used = int(size["used_diram"])
        total = int(size["diram_total"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise DemoError("could not parse esp-idf-size JSON output") from error
    if remaining < MIN_DIRAM_REMAIN:
        raise DemoError(
            f"{profile} leaves only {remaining} B DIRAM; "
            f"the safety floor is {MIN_DIRAM_REMAIN} B"
        )
    print(f"OK  {profile} DIRAM: {used}/{total} B, {remaining} B link margin")


def cmd_build(args: argparse.Namespace) -> None:
    cmd_check(args)
    if args.profile != "probe":
        verify_asset(ASSET_SPECS["model"], ASSETS / str(ASSET_SPECS["model"]["name"]))
    if args.profile == "kanji":
        verify_asset(ASSET_SPECS["dict"], ASSETS / str(ASSET_SPECS["dict"]["name"]))
    profile, build_dir, definitions = build_parameters(args.profile, args.silent)
    command = [idf_command(), "-B", str(build_dir)] + definitions
    if args.reconfigure:
        # Regenerate this profile only; configs are generated files inside its
        # own ignored build directory, never user source configuration.
        (build_dir / "sdkconfig").unlink(missing_ok=True)
        (build_dir / "sdkconfig.old").unlink(missing_ok=True)
        run(command + ["reconfigure"], cwd=FIRMWARE)
    run(command + ["build"], cwd=FIRMWARE)
    check_build_margin(profile, build_dir)
    DIST.mkdir(parents=True, exist_ok=True)
    merged = DIST / f"rlcd42-sanotts-{profile}.bin"
    run(command + ["merge-bin", "-o", str(merged)], cwd=FIRMWARE)
    verify_built_capabilities(merged, profile)
    for source, destination_name in DIST_NOTICE_FILES.items():
        shutil.copyfile(source, DIST / destination_name)
    print(f"OK  build: {build_dir.relative_to(ROOT)}")
    print(f"OK  merged image: {merged.relative_to(ROOT)} sha256={sha256_file(merged)}")
    print("OK  redistribution notices copied beside the merged image")


def matching_backup(device: dict[str, object]) -> pathlib.Path:
    mac = str(device["mac"])
    security = device.get("security_state")
    candidates: list[tuple[str, pathlib.Path]] = []
    for manifest_path in BACKUPS.glob("rlcd42-backup-*.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict):
                continue
            image = BACKUPS / manifest["image"]
            if str(manifest.get("mac", "")).lower() != mac.lower() or not image.exists():
                continue
            validate_backup_manifest(manifest, image)
            if manifest.get("security") != security:
                continue
            if manifest.get("role") != "recovery-baseline":
                continue
            candidates.append((manifest_path.name, image))
        except (DemoError, OSError, KeyError, ValueError, TypeError):
            continue
    if not candidates:
        raise DemoError(f"no verified two-read 16 MiB backup matches device MAC {mac}; run backup first")
    return min(candidates)[1]


def has_recovery_baseline(mac: str, security: object) -> bool:
    try:
        matching_backup({"mac": mac, "security_state": security})
        return True
    except DemoError:
        return False


def cmd_flash(args: argparse.Namespace) -> None:
    require_board_confirmation(args.confirm_board)
    if args.profile != "probe" and not args.silent and not args.yes_speaker_connected:
        raise DemoError(
            "audio output requires the board powered off, the supplied speaker firmly connected, "
            "and --yes-speaker-connected"
        )
    info = inspect_device(args.port, require_unsecured=True)
    backup = matching_backup(info)
    print(f"OK  recovery image: {backup}")
    cmd_build(args)
    # A fresh build can take several minutes. Re-identify the target immediately
    # before the write so a disconnect/reconnect or serial-port reassignment
    # cannot silently redirect this operation to a different ESP32-S3 board.
    final_info = inspect_device(args.port, require_unsecured=True)
    if (final_info["mac"] != info["mac"] or
            final_info["security_state"] != info["security_state"]):
        raise DemoError(
            "device MAC or security state changed during build; refusing to flash"
        )
    manifest = load_restore_manifest(backup)
    if (manifest is None or str(manifest.get("mac", "")).lower() != final_info["mac"] or
            manifest.get("security") != final_info["security_state"] or
            manifest.get("role") != "recovery-baseline"):
        raise DemoError("recovery baseline changed during build; refusing to flash")
    _, build_dir, _ = build_parameters(args.profile, args.silent)
    run([idf_command(), "-B", str(build_dir), "-p", args.port, "flash"], cwd=FIRMWARE)
    if args.profile == "probe":
        print("OK  model-free board probe written; PA stays disabled")
    elif args.silent:
        print("OK  silent TTS firmware written; ES8311/I2S/PA are compiled out")
    else:
        print("OK  audio firmware written. Boot remains silent; only demo/input speaks.")


def cmd_monitor(args: argparse.Namespace) -> None:
    _, build_dir, _ = build_parameters(args.profile, args.silent)
    if not build_dir.exists():
        raise DemoError("build directory is missing; run build first")
    run([idf_command(), "-B", str(build_dir), "-p", args.port, "monitor"], cwd=FIRMWARE)


def cmd_demo(args: argparse.Namespace) -> None:
    if args.profile == "probe":
        raise DemoError("the model-free probe has no TTS console; use monitor")
    require_board_confirmation(args.confirm_board)
    if not args.silent and not args.yes_speaker_connected:
        raise DemoError("audio demo requires --yes-speaker-connected; use --silent for silent firmware")
    message = getattr(args, "message", None)
    if message is not None:
        if args.profile != "kanji":
            raise DemoError("--message requires the kanji firmware profile")
        if not message or message.startswith("!"):
            raise DemoError("--message must be non-empty ordinary Japanese without a leading !")
        phrase = "!" + message
    else:
        phrase = args.text if args.text is not None else (
            DEMO_KANJI if args.profile == "kanji" else DEMO_KANA
        )
    if "\r" in phrase or "\n" in phrase:
        raise DemoError("the demo text must be exactly one line")
    expected_profile, _, _ = build_parameters(args.profile, args.silent)
    installed_profile = detect_installed_profile(args.port)
    if installed_profile != expected_profile:
        raise DemoError(
            f"installed firmware is {installed_profile}, but this command requested "
            f"{expected_profile}; no utterance was sent"
        )
    print(f"OK  installed firmware profile: {installed_profile}")
    try:
        import serial  # type: ignore
    except ImportError as error:
        raise DemoError(
            "pyserial is required: python3 -m pip install pyserial "
            "(Windows: python -m pip install pyserial)"
        ) from error
    deadline = time.monotonic() + args.timeout
    expected_start = (
        "RLCD42_SILENT_START:OK" if args.silent
        else "RLCD42_AUDIO_START:OK PA=HIGH VOLUME=100"
    )
    expected_result = (
        "RLCD42_SILENT_RESULT:OK PA=COMPILED_OUT" if args.silent
        else "RLCD42_AUDIO_RESULT:OK PA=LOW"
    )
    failure_markers = (
        "RLCD42_AUDIO_START:FAIL",
        "RLCD42_AUDIO_RESULT:FAIL",
        "RLCD42_SILENT_RESULT:FAIL",
    )
    saw_start = False
    saw_metrics = False
    saw_result = False
    sent = False
    buffer = ""
    with serial.Serial(args.port, 115200, timeout=0.2, write_timeout=2) as port:
        port.reset_input_buffer()
        # A blank line is harmless and makes an already-running console emit a
        # fresh prompt; if the board is rebooting it is consumed once ready.
        port.write(b"\r\n")
        port.flush()
        while time.monotonic() < deadline:
            chunk = port.read(4096)
            if not chunk:
                continue
            text = chunk.decode("utf-8", errors="replace")
            print(text, end="", flush=True)
            buffer = (buffer + text)[-16384:]
            if not sent and "かな> " in buffer:
                sent = True
                buffer = ""
                print(f"\nSending: {phrase}")
                port.write((phrase + "\r\n").encode("utf-8"))
                port.flush()
                continue
            if sent:
                if any(marker in buffer for marker in failure_markers):
                    raise DemoError("firmware reported an explicit audio/synthesis failure")
                saw_start = saw_start or expected_start in buffer
                saw_metrics = saw_metrics or "----- 結果 -----" in buffer
                saw_result = saw_result or expected_result in buffer
                if "かな> " in buffer:
                    if saw_start and saw_metrics and saw_result:
                        print("\nOK  synthesis, codec readback and PA shutdown verified")
                        return
                    raise DemoError(
                        "firmware returned to the prompt without the required verified result marker"
                    )
    stage = "ready prompt" if not sent else "synthesis result"
    raise DemoError(f"timed out waiting for {stage}; run monitor and inspect the boot log")


def validate_backup_manifest(manifest: dict[str, object], image: pathlib.Path) -> None:
    if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("chip") != "ESP32-S3":
        raise DemoError("backup manifest schema or chip is not supported")
    if manifest.get("device") != BOARD_NAME or manifest.get("board") != BOARD_ID:
        raise DemoError("backup manifest belongs to a different board")
    expected_confirmation = {"method": "typed-silkscreen", "value": BOARD_ID}
    if manifest.get("board_confirmation") != expected_confirmation:
        raise DemoError("backup manifest lacks the required physical-board confirmation")
    if manifest.get("flash_bytes") != FLASH_BYTES or manifest.get("reads") != 2:
        raise DemoError("backup manifest is not an accepted two-read 16 MiB backup")
    if manifest.get("role") not in {"recovery-baseline", "snapshot"}:
        raise DemoError("backup manifest has no valid recovery role")
    if manifest.get("image") != image.name:
        raise DemoError("backup manifest points to a different image")
    mac = str(manifest.get("mac", ""))
    if not re.fullmatch(r"[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}", mac):
        raise DemoError("backup manifest has an invalid MAC address")
    digest = str(manifest.get("sha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise DemoError("backup manifest has an invalid SHA-256")
    security = manifest.get("security")
    if not isinstance(security, dict) or set(security) != {"secure_boot", "flash_encryption"}:
        raise DemoError("backup manifest has no normalized security state")
    if any(value not in {"enabled", "disabled", "unknown"} for value in security.values()):
        raise DemoError("backup manifest security state is invalid")
    for field in ("security_output_sha256", "flash_probe_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get(field, ""))):
            raise DemoError(f"backup manifest has an invalid {field}")
    markers = manifest.get("factory_markers")
    if not isinstance(markers, list):
        raise DemoError("backup manifest factory marker evidence is invalid")
    allowed_markers = {marker.decode("ascii") for marker in FACTORY_MARKERS}
    for marker in markers:
        if (not isinstance(marker, dict) or marker.get("text") not in allowed_markers or
                not isinstance(marker.get("offset"), int) or not 0 <= int(marker["offset"]) < FLASH_BYTES):
            raise DemoError("backup manifest contains invalid factory marker evidence")
    if not image.is_file() or image.stat().st_size != FLASH_BYTES:
        raise DemoError("backup image is not an exact 16 MiB file")
    if sha256_file(image) != digest:
        raise DemoError("backup image SHA-256 does not match its manifest")


def load_restore_manifest(image: pathlib.Path) -> dict[str, object] | None:
    adjacent = image.with_suffix(".json")
    if not adjacent.exists():
        return None
    manifest = json.loads(adjacent.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise DemoError("backup manifest must be a JSON object")
    validate_backup_manifest(manifest, image)
    return manifest


def cmd_restore(args: argparse.Namespace) -> None:
    require_board_confirmation(args.confirm_board)
    image = pathlib.Path(args.image).expanduser().resolve()
    if not image.is_file() or image.stat().st_size != FLASH_BYTES:
        raise DemoError("restore image must be an existing, exact 16 MiB file")
    manifest = load_restore_manifest(image)
    if manifest is None:
        raise DemoError("restore requires the matching .json manifest created by backup")
    info = inspect_device(args.port, require_unsecured=True)
    if str(manifest.get("mac", "")).lower() != info["mac"]:
        raise DemoError("backup MAC does not match the connected device")
    if manifest.get("security") != info["security_state"]:
        raise DemoError("backup and connected device security states do not match")
    if args.dry_run:
        print(f"OK  restore dry-run: board, MAC, security, size and SHA-256 match: {image}")
        return
    if not args.yes:
        raise DemoError("restore overwrites the full flash; rerun with --yes after checking the image and port")
    digest = sha256_file(image)
    if digest != manifest.get("sha256"):
        raise DemoError("restore image changed after validation; refusing to write")
    print(f"Restoring {image} sha256={digest}")
    final_info = inspect_device(args.port, require_unsecured=True)
    if (final_info["mac"] != info["mac"] or
            final_info["security_state"] != info["security_state"]):
        raise DemoError(
            "device MAC or security state changed before restore; refusing to write"
        )
    if sha256_file(image) != digest:
        raise DemoError("restore image changed immediately before write; refusing to write")
    esptool(args.port, [
        "write_flash", "--flash_mode", "keep", "--flash_freq", "keep",
        "--flash_size", "keep", "0x0", str(image),
    ])
    esptool(args.port, ["verify_flash", "0x0", str(image)])
    restored_info = inspect_device(args.port, require_unsecured=True)
    if (restored_info["mac"] != info["mac"] or
            restored_info["security_state"] != info["security_state"]):
        raise DemoError("restore verified, but post-restore device identity or security state changed")
    print("OK  full-flash restore and verification completed")


def cmd_ports(_: argparse.Namespace) -> None:
    try:
        from serial.tools import list_ports  # type: ignore
    except ImportError as error:
        raise DemoError(
            "pyserial is required: python3 -m pip install pyserial "
            "(Windows: python -m pip install pyserial)"
        ) from error
    found = list(list_ports.comports())
    if not found:
        print("No serial ports found.")
        return
    for port in found:
        print(f"{port.device:16} {port.description} [{port.hwid}]")


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(description=__doc__)
    commands = top.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="verify repository safety invariants")
    check.set_defaults(func=cmd_check)

    fetch = commands.add_parser("fetch", help="download and hash-check separately licensed assets")
    fetch.add_argument("--kanji", action="store_true", help="also fetch the 13.7 MB kanji dictionary")
    fetch.add_argument("--accept-model-license", action="store_true", help="confirm licenses/sanoTTS-jp-model.md was read and accepted")
    fetch.set_defaults(func=cmd_fetch)

    ports = commands.add_parser("ports", help="list serial ports (requires pyserial)")
    ports.set_defaults(func=cmd_ports)

    doctor = commands.add_parser("doctor", help="check repository, chip, flash size, and security state")
    doctor.add_argument("--port", required=True)
    doctor.add_argument("--confirm-board", required=True, metavar=BOARD_ID)
    doctor.set_defaults(func=cmd_doctor)

    backup = commands.add_parser("backup", help="read full factory flash twice and compare")
    backup.add_argument("--port", required=True)
    backup.add_argument("--confirm-board", required=True, metavar=BOARD_ID)
    backup.set_defaults(func=cmd_backup)

    for name, function, help_text in (
        ("build", cmd_build, "build and create a merged 16 MB-layout image"),
        ("flash", cmd_flash, "build and flash after verifying a matching backup"),
        ("monitor", cmd_monitor, "open the ESP-IDF serial monitor"),
    ):
        item = commands.add_parser(name, help=help_text)
        item.add_argument("--profile", choices=PROFILES,
                          required=name == "flash", default=None if name == "flash" else "kana")
        item.add_argument("--silent", action="store_true",
                          help="compile out ES8311, I2S and PA while retaining TTS metrics")
        if name == "build":
            item.add_argument("--reconfigure", action="store_true")
        elif name == "flash":
            item.add_argument("--reconfigure", action="store_true")
            item.add_argument("--port", required=True)
            item.add_argument("--confirm-board", required=True, metavar=BOARD_ID)
            item.add_argument("--yes-speaker-connected", action="store_true")
        else:
            item.add_argument("--port", required=True)
        item.set_defaults(func=function)

    demo = commands.add_parser("demo", help="send the deterministic demo phrase and wait for metrics")
    demo.add_argument("--port", required=True)
    demo.add_argument("--confirm-board", required=True, metavar=BOARD_ID)
    demo.add_argument("--profile", choices=PROFILES, default="kana")
    demo.add_argument("--silent", action="store_true", help="confirm the installed firmware has audio compiled out")
    demo.add_argument("--yes-speaker-connected", action="store_true")
    content = demo.add_mutually_exclusive_group()
    content.add_argument("--text", help="one raw kana-intermediate line; use a leading ! with kanji firmware")
    content.add_argument("--message", help="ordinary Japanese text; automatically adds ! and requires --profile kanji")
    demo.add_argument("--timeout", type=float, default=90.0)
    demo.set_defaults(func=cmd_demo)

    restore = commands.add_parser("restore", help="restore and verify one full 16 MiB backup")
    restore.add_argument("image")
    restore.add_argument("--port", required=True)
    restore.add_argument("--confirm-board", required=True, metavar=BOARD_ID)
    restore.add_argument("--dry-run", action="store_true", help="validate without writing flash")
    restore.add_argument("--yes", action="store_true", help="confirm full-flash overwrite")
    restore.set_defaults(func=cmd_restore)
    return top


def main() -> int:
    args = parser().parse_args()
    try:
        args.func(args)
        return 0
    except (DemoError, OSError, urllib.error.URLError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
