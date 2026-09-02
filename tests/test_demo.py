from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import sys
import tempfile
import types
import unittest
from argparse import Namespace
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("rlcd42_demo", ROOT / "tools/demo.py")
assert SPEC and SPEC.loader
demo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(demo)


MAC_A = "aa:bb:cc:dd:ee:01"
MAC_B = "aa:bb:cc:dd:ee:02"
DISABLED_SECURITY = {"secure_boot": "disabled", "flash_encryption": "disabled"}


def device(mac: str = MAC_A, security: dict[str, str] | None = None) -> dict[str, object]:
    return {
        "mac": mac,
        "security_state": dict(security or DISABLED_SECURITY),
        "security": "Secure Boot: Disabled\nFlash Encryption: Disabled\n",
        "flash": "Detected flash size: 16MB\n",
    }


def valid_manifest(
    image: pathlib.Path,
    *,
    mac: str = MAC_A,
    security: dict[str, str] | None = None,
    markers: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema": demo.MANIFEST_SCHEMA,
        "device": demo.BOARD_NAME,
        "board": demo.BOARD_ID,
        "board_confirmation": {
            "method": "typed-silkscreen",
            "value": demo.BOARD_ID,
        },
        "chip": "ESP32-S3",
        "flash_bytes": demo.FLASH_BYTES,
        "mac": mac,
        "security": dict(security or DISABLED_SECURITY),
        "security_output_sha256": "1" * 64,
        "flash_probe_sha256": "2" * 64,
        "image": image.name,
        "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        "reads": 2,
        "role": "recovery-baseline",
        "factory_markers": list(markers or []),
    }


class DemoToolTests(unittest.TestCase):
    def test_mac_parser_accepts_label_and_fallback_but_rejects_missing_identity(self) -> None:
        self.assertEqual(
            demo.parse_mac("Chip is ESP32-S3\nMAC: AA:bb:01:02:03:04\n"),
            "aa:bb:01:02:03:04",
        )
        self.assertEqual(
            demo.parse_mac("Base MAC address aa:BB:cc:00:11:22"),
            "aa:bb:cc:00:11:22",
        )
        with self.assertRaises(demo.DemoError):
            demo.parse_mac("no device identity here")

    def test_security_parsers_are_fail_closed(self) -> None:
        disabled = "Secure Boot: Disabled\nFlash Encryption: Disabled\n"
        self.assertFalse(demo.security_is_enabled(disabled))
        self.assertEqual(demo.normalized_security(disabled), DISABLED_SECURITY)

        self.assertTrue(demo.security_is_enabled("Secure Boot: Enabled\n"))
        self.assertTrue(demo.security_is_enabled("Flash encryption is enabled\n"))
        self.assertEqual(
            demo.normalized_security("Secure Boot: Enabled\nFlash Encryption: Disabled\n"),
            {"secure_boot": "enabled", "flash_encryption": "disabled"},
        )
        self.assertEqual(
            demo.normalized_security("FLASH_CRYPT_CNT is odd (enabled)\n"),
            {"secure_boot": "unknown", "flash_encryption": "enabled"},
        )
        for unsafe in (
            {"secure_boot": "unknown", "flash_encryption": "disabled"},
            {"secure_boot": "disabled", "flash_encryption": "enabled"},
        ):
            with self.assertRaisesRegex(demo.DemoError, "could not be proven disabled"):
                demo.require_unsecured_state(unsafe)

    def test_probe_kana_silent_and_kanji_have_isolated_sdkconfigs(self) -> None:
        cases = (
            ("probe", False, "probe", "-DSAAN_BOARD_PROBE=1"),
            ("kana", False, "kana", "-DSAAN_ENABLE_PIE=1"),
            ("kana", True, "kana-silent", "-DSAAN_SILENT=1"),
            ("kanji", False, "kanji", "-DSAAN_KANJI=1"),
        )
        sdkconfigs: set[pathlib.Path] = set()
        for profile, silent, expected_name, required_definition in cases:
            name, build_dir, definitions = demo.build_parameters(profile, silent)
            self.assertEqual(name, expected_name)
            sdkconfig = build_dir / "sdkconfig"
            self.assertIn(f"-DSDKCONFIG={sdkconfig}", definitions)
            self.assertIn(required_definition, definitions)
            sdkconfigs.add(sdkconfig)
        self.assertEqual(len(sdkconfigs), len(cases))
        with self.assertRaises(demo.DemoError):
            demo.build_parameters("probe", True)
        with self.assertRaises(demo.DemoError):
            demo.build_parameters("not-a-profile")

    def test_factory_marker_scanner_recognizes_all_three_markers_and_none(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            image = pathlib.Path(temporary) / "factory.bin"
            for marker in demo.FACTORY_MARKERS:
                image.write_bytes(b"prefix:" + marker + b":suffix")
                self.assertEqual(
                    demo.find_factory_markers(image),
                    [{"text": marker.decode("ascii"), "offset": 7}],
                )
            image.write_bytes(b"no known product identity")
            self.assertEqual(demo.find_factory_markers(image), [])

    def test_manifest_validates_board_confirmation_security_reads_size_hash_and_role(self) -> None:
        payload = b"0123456789abcdef"
        with mock.patch.object(demo, "FLASH_BYTES", len(payload)):
            with tempfile.TemporaryDirectory() as temporary:
                image = pathlib.Path(temporary) / "factory.bin"
                image.write_bytes(payload)
                manifest = valid_manifest(image)
                demo.validate_backup_manifest(manifest, image)

                mutations: tuple[tuple[str, object, str], ...] = (
                    ("schema", 1, "schema or chip"),
                    ("board", "M5Stack-CoreS3", "different board"),
                    ("board_confirmation", None, "physical-board confirmation"),
                    ("reads", 1, "two-read 16 MiB"),
                    ("role", "unknown", "recovery role"),
                    ("flash_bytes", len(payload) + 1, "two-read 16 MiB"),
                    ("security", {"secure_boot": "disabled"}, "normalized security"),
                    ("security_output_sha256", "bad", "security_output_sha256"),
                    ("flash_probe_sha256", "bad", "flash_probe_sha256"),
                    ("sha256", "0" * 64, "does not match"),
                )
                for field, bad_value, error in mutations:
                    broken = dict(manifest)
                    broken[field] = bad_value
                    with self.subTest(field=field):
                        with self.assertRaisesRegex(demo.DemoError, error):
                            demo.validate_backup_manifest(broken, image)

                image.write_bytes(payload[:-1])
                with self.assertRaisesRegex(demo.DemoError, "exact 16 MiB"):
                    demo.validate_backup_manifest(manifest, image)

    def test_profile_markers_are_exact_and_ambiguous_images_are_rejected(self) -> None:
        for name, marker in demo.PROFILE_MARKERS.items():
            with self.subTest(name=name):
                self.assertEqual(demo.parse_installed_profile(b"prefix" + marker + b"suffix"), name)
        with self.assertRaisesRegex(demo.DemoError, "found: none"):
            demo.parse_installed_profile(b"not an RLCD demo")
        with self.assertRaisesRegex(demo.DemoError, "kana, kana-silent"):
            demo.parse_installed_profile(
                demo.PROFILE_MARKERS["kana"] + demo.PROFILE_MARKERS["kana-silent"]
            )

    def test_silent_demo_refuses_an_installed_audio_profile_before_serial_io(self) -> None:
        args = Namespace(
            port="TEST", confirm_board=demo.BOARD_ID, profile="kana", silent=True,
            yes_speaker_connected=False, text=None, timeout=1.0,
        )
        with (
            mock.patch.object(demo, "inspect_device", return_value=device()),
            mock.patch.object(demo, "matching_backup", return_value=ROOT / "factory.bin"),
            mock.patch.object(demo, "detect_installed_profile", return_value="kana"),
        ):
            with self.assertRaisesRegex(demo.DemoError, "no utterance was sent"):
                demo.cmd_demo(args)

    def test_manifest_accepts_each_known_marker_or_no_marker_after_typed_confirmation(self) -> None:
        payload = b"0123456789abcdef"
        with mock.patch.object(demo, "FLASH_BYTES", len(payload)):
            with tempfile.TemporaryDirectory() as temporary:
                image = pathlib.Path(temporary) / "factory.bin"
                image.write_bytes(payload)
                evidence = [
                    [],
                    *[[{"text": marker.decode("ascii"), "offset": 0}]
                      for marker in demo.FACTORY_MARKERS],
                ]
                for markers in evidence:
                    with self.subTest(markers=markers):
                        demo.validate_backup_manifest(
                            valid_manifest(image, markers=markers), image
                        )

                broken = valid_manifest(
                    image, markers=[{"text": "another-board", "offset": 0}]
                )
                with self.assertRaisesRegex(demo.DemoError, "marker evidence"):
                    demo.validate_backup_manifest(broken, image)

    def test_wrong_or_missing_board_confirmation_is_rejected(self) -> None:
        expected = {"method": "typed-silkscreen", "value": demo.BOARD_ID}
        self.assertEqual(demo.require_board_confirmation(demo.BOARD_ID), expected)
        for value in (None, "", "M5Stack-CoreS3", demo.BOARD_ID.lower()):
            with self.subTest(value=value):
                with self.assertRaisesRegex(demo.DemoError, "physical board silkscreen"):
                    demo.require_board_confirmation(value)

    def test_mutating_commands_require_explicit_board_confirmation_before_io(self) -> None:
        with mock.patch.object(demo, "inspect_device") as inspect:
            with self.assertRaises(demo.DemoError):
                demo.cmd_backup(Namespace(port="TEST", confirm_board="wrong"))
            with self.assertRaises(demo.DemoError):
                demo.cmd_flash(Namespace(
                    port="TEST", confirm_board="wrong", profile="kana", silent=True,
                    yes_speaker_connected=False, reconfigure=False,
                ))
            with self.assertRaises(demo.DemoError):
                demo.cmd_restore(Namespace(
                    port="TEST", confirm_board="wrong", image="missing.bin",
                    dry_run=False, yes=True,
                ))
        inspect.assert_not_called()

    def test_backup_rejects_mismatched_reads_without_accepting_an_image(self) -> None:
        with mock.patch.object(demo, "FLASH_BYTES", 16):
            with tempfile.TemporaryDirectory() as temporary:
                backup_dir = pathlib.Path(temporary) / "backups"
                read_number = 0

                def fake_esptool(_port: str, operation: list[str], **_kwargs: object) -> None:
                    nonlocal read_number
                    if operation[0] == "read_flash":
                        read_number += 1
                        byte = b"a" if read_number == 1 else b"b"
                        pathlib.Path(operation[-1]).write_bytes(byte * 16)

                with (
                    mock.patch.object(demo, "BACKUPS", backup_dir),
                    mock.patch.object(demo, "inspect_device", return_value=device()),
                    mock.patch.object(demo, "esptool", side_effect=fake_esptool),
                ):
                    with self.assertRaisesRegex(demo.DemoError, "two full-flash reads differ"):
                        demo.cmd_backup(Namespace(
                            port="TEST", confirm_board=demo.BOARD_ID
                        ))
                self.assertEqual(list(backup_dir.iterdir()), [])

    def test_backup_rejects_device_swap_after_two_reads(self) -> None:
        with mock.patch.object(demo, "FLASH_BYTES", 16):
            with tempfile.TemporaryDirectory() as temporary:
                backup_dir = pathlib.Path(temporary) / "backups"

                def fake_esptool(_port: str, operation: list[str], **_kwargs: object) -> None:
                    if operation[0] == "read_flash":
                        pathlib.Path(operation[-1]).write_bytes(b"x" * 16)

                with (
                    mock.patch.object(demo, "BACKUPS", backup_dir),
                    mock.patch.object(
                        demo, "inspect_device", side_effect=[device(MAC_A), device(MAC_B)]
                    ) as inspect,
                    mock.patch.object(demo, "esptool", side_effect=fake_esptool),
                ):
                    with self.assertRaisesRegex(demo.DemoError, "device MAC changed"):
                        demo.cmd_backup(Namespace(
                            port="TEST", confirm_board=demo.BOARD_ID
                        ))
                self.assertEqual(inspect.call_count, 2)
                self.assertEqual(list(backup_dir.iterdir()), [])

    def test_flash_rejects_device_swap_after_build(self) -> None:
        args = Namespace(
            port="TEST", confirm_board=demo.BOARD_ID, profile="kana", silent=True,
            yes_speaker_connected=False, reconfigure=False,
        )
        with (
            mock.patch.object(
                demo, "inspect_device", side_effect=[device(MAC_A), device(MAC_B)]
            ) as inspect,
            mock.patch.object(demo, "matching_backup", return_value=ROOT / "factory.bin"),
            mock.patch.object(demo, "cmd_build"),
            mock.patch.object(demo, "run") as run,
        ):
            with self.assertRaisesRegex(demo.DemoError, "MAC or security state changed"):
                demo.cmd_flash(args)
        self.assertEqual(inspect.call_count, 2)
        run.assert_not_called()

    def test_flash_revalidates_recovery_baseline_after_build(self) -> None:
        payload = b"0123456789abcdef"
        with mock.patch.object(demo, "FLASH_BYTES", len(payload)):
            with tempfile.TemporaryDirectory() as temporary:
                image = pathlib.Path(temporary) / "baseline.bin"
                image.write_bytes(payload)
                image.with_suffix(".json").write_text(
                    json.dumps(valid_manifest(image)), encoding="utf-8"
                )
                args = Namespace(
                    port="TEST", confirm_board=demo.BOARD_ID, profile="kana", silent=True,
                    yes_speaker_connected=False, reconfigure=False,
                )

                def mutate_backup(_args: object) -> None:
                    image.write_bytes(b"x" * len(payload))

                with (
                    mock.patch.object(demo, "inspect_device", return_value=device()),
                    mock.patch.object(demo, "matching_backup", return_value=image),
                    mock.patch.object(demo, "cmd_build", side_effect=mutate_backup),
                    mock.patch.object(demo, "run") as run,
                ):
                    with self.assertRaisesRegex(demo.DemoError, "SHA-256"):
                        demo.cmd_flash(args)
                run.assert_not_called()

    def test_restore_rejects_manifest_device_security_mismatch(self) -> None:
        payload = b"0123456789abcdef"
        with mock.patch.object(demo, "FLASH_BYTES", len(payload)):
            with tempfile.TemporaryDirectory() as temporary:
                image = pathlib.Path(temporary) / "factory.bin"
                image.write_bytes(payload)
                image.with_suffix(".json").write_text(
                    json.dumps(valid_manifest(image)), encoding="utf-8"
                )
                args = Namespace(
                    port="TEST", confirm_board=demo.BOARD_ID, image=str(image),
                    dry_run=False, yes=True,
                )
                enabled = {"secure_boot": "enabled", "flash_encryption": "disabled"}
                with (
                    mock.patch.object(demo, "inspect_device", return_value=device(MAC_A, enabled)),
                    mock.patch.object(demo, "esptool") as esptool,
                ):
                    with self.assertRaisesRegex(demo.DemoError, "security states do not match"):
                        demo.cmd_restore(args)
                esptool.assert_not_called()

    def test_restore_rejects_device_swap_immediately_before_write(self) -> None:
        payload = b"0123456789abcdef"
        with mock.patch.object(demo, "FLASH_BYTES", len(payload)):
            with tempfile.TemporaryDirectory() as temporary:
                image = pathlib.Path(temporary) / "factory.bin"
                image.write_bytes(payload)
                image.with_suffix(".json").write_text(
                    json.dumps(valid_manifest(image)), encoding="utf-8"
                )
                args = Namespace(
                    port="TEST", confirm_board=demo.BOARD_ID, image=str(image),
                    dry_run=False, yes=True,
                )
                with (
                    mock.patch.object(
                        demo, "inspect_device", side_effect=[device(MAC_A), device(MAC_B)]
                    ) as inspect,
                    mock.patch.object(demo, "esptool") as esptool,
                ):
                    with self.assertRaisesRegex(demo.DemoError, "changed before restore"):
                        demo.cmd_restore(args)
                self.assertEqual(inspect.call_count, 2)
                esptool.assert_not_called()

    def test_restore_rehashes_image_immediately_before_write(self) -> None:
        payload = b"0123456789abcdef"
        digest = hashlib.sha256(payload).hexdigest()
        with mock.patch.object(demo, "FLASH_BYTES", len(payload)):
            with tempfile.TemporaryDirectory() as temporary:
                image = pathlib.Path(temporary) / "factory.bin"
                image.write_bytes(payload)
                image.with_suffix(".json").write_text(
                    json.dumps(valid_manifest(image)), encoding="utf-8"
                )
                args = Namespace(
                    port="TEST", confirm_board=demo.BOARD_ID, image=str(image),
                    dry_run=False, yes=True,
                )
                with (
                    mock.patch.object(demo, "inspect_device", return_value=device()),
                    mock.patch.object(
                        demo, "sha256_file", side_effect=[digest, digest, "0" * 64]
                    ),
                    mock.patch.object(demo, "esptool") as esptool,
                ):
                    with self.assertRaisesRegex(demo.DemoError, "immediately before write"):
                        demo.cmd_restore(args)
                esptool.assert_not_called()

    def test_restore_uses_three_keep_options_and_never_erases(self) -> None:
        payload = b"0123456789abcdef"
        with mock.patch.object(demo, "FLASH_BYTES", len(payload)):
            with tempfile.TemporaryDirectory() as temporary:
                image = pathlib.Path(temporary) / "factory.bin"
                image.write_bytes(payload)
                image.with_suffix(".json").write_text(
                    json.dumps(valid_manifest(image)), encoding="utf-8"
                )
                args = Namespace(
                    port="TEST", confirm_board=demo.BOARD_ID, image=str(image),
                    dry_run=False, yes=True,
                )
                with (
                    mock.patch.object(demo, "inspect_device", return_value=device()),
                    mock.patch.object(demo, "esptool") as esptool,
                ):
                    demo.cmd_restore(args)

                self.assertEqual(esptool.call_count, 2)
                write = esptool.call_args_list[0].args[1]
                verify = esptool.call_args_list[1].args[1]
                self.assertEqual(write[0], "write_flash")
                self.assertEqual(write.count("keep"), 3)
                self.assertEqual(
                    write,
                    [
                        "write_flash",
                        "--flash_mode", "keep",
                        "--flash_freq", "keep",
                        "--flash_size", "keep",
                        "0x0", str(image.resolve()),
                    ],
                )
                self.assertEqual(verify, ["verify_flash", "0x0", str(image.resolve())])
                self.assertFalse(any("erase" in token.lower() for token in write + verify))

    def test_matching_backup_uses_baseline_and_never_newer_snapshot(self) -> None:
        payload = b"0123456789abcdef"
        with mock.patch.object(demo, "FLASH_BYTES", len(payload)):
            with tempfile.TemporaryDirectory() as temporary:
                backup_dir = pathlib.Path(temporary)
                baseline = backup_dir / "rlcd42-backup-20260101T000000-000000+0900-aabbccddee01.bin"
                snapshot = backup_dir / "rlcd42-backup-20260102T000000-000000+0900-aabbccddee01.bin"
                for image, role in ((baseline, "recovery-baseline"), (snapshot, "snapshot")):
                    image.write_bytes(payload)
                    manifest = valid_manifest(image)
                    manifest["role"] = role
                    image.with_suffix(".json").write_text(json.dumps(manifest), encoding="utf-8")
                with mock.patch.object(demo, "BACKUPS", backup_dir):
                    self.assertEqual(demo.matching_backup(device()), baseline)

    def test_firmware_keeps_pa_interlock_and_silent_compile_gate(self) -> None:
        entry = (ROOT / "firmware/main/rlcd42_entry.c").read_text(encoding="utf-8")
        board = (ROOT / "firmware/main/rlcd42_board.c").read_text(encoding="utf-8")
        audio = (ROOT / "firmware/main/rlcd42_saan_i2s.c").read_text(encoding="utf-8")
        cmake = (ROOT / "firmware/main/CMakeLists.txt").read_text(encoding="utf-8")

        self.assertLess(entry.index("rlcd42_board_init()"), entry.index("saan_upstream_app_main()"))
        self.assertLess(board.index("gpio_set_level(RLCD42_PA_EN, 0)"), board.index("gpio_config(&cfg)"))
        self.assertIn(".pa_pin = GPIO_NUM_NC", audio)
        self.assertIn("rlcd42_board_set_amp_enabled(true)", audio)
        self.assertIn("write_mono_chunks(s_preroll, s_preroll_fill)", audio)
        self.assertIn("samples > SAAN_I2S_MAXBUF", audio)
        self.assertIn("SAAN_SKIP_I2S=1", cmake)
        self.assertNotIn("stackchan_", cmake.lower())

    def test_battery_adc_contract_is_calibrated_multisampled_and_advisory(self) -> None:
        battery = (ROOT / "firmware/main/rlcd42_battery.c").read_text(encoding="utf-8")
        header = (ROOT / "firmware/main/rlcd42_battery.h").read_text(encoding="utf-8")
        probe = (ROOT / "firmware/main/rlcd42_probe.c").read_text(encoding="utf-8")
        audio = (ROOT / "firmware/main/rlcd42_saan_i2s.c").read_text(encoding="utf-8")
        cmake = (ROOT / "firmware/main/CMakeLists.txt").read_text(encoding="utf-8")

        for token in (
            "RLCD42_BATTERY_ADC_UNIT    ADC_UNIT_1",
            "RLCD42_BATTERY_ADC_CHANNEL ADC_CHANNEL_3",
            "RLCD42_BATTERY_ADC_GPIO    GPIO_NUM_4",
            "RLCD42_BATTERY_DIVIDER     3u",
            "RLCD42_BATTERY_SAMPLES     16u",
            "RLCD42_BATTERY_EXPECTED_MAX_MV 4200u",
            "ADC_ATTEN_DB_12",
            "ADC_BITWIDTH_12",
            "adc_oneshot_io_to_channel",
            "adc_cali_create_scheme_curve_fitting",
            "adc_cali_raw_to_voltage",
        ):
            with self.subTest(token=token):
                self.assertIn(token, battery)
        self.assertIn("voltage_available", header)
        self.assertIn("in_expected_range", header)
        self.assertIn("status->voltage_available = true;", battery)
        self.assertNotIn("RLCD42_BATTERY_DETECTED_MV", battery)
        self.assertIn("rlcd42_battery_init()", probe)
        self.assertIn("rlcd42_battery_read(&battery)", probe)
        self.assertIn("battery telemetry unavailable; USB/audio operation will continue", audio)
        self.assertEqual(cmake.count('"rlcd42_battery.c"'), 2)
        self.assertGreaterEqual(cmake.count("esp_adc"), 2)

        bringup = (ROOT / "docs/bringup.md").read_text(encoding="utf-8")
        self.assertIn("3.00～4.20 Vの有効な `BAT x.xxV`", bringup)
        self.assertIn("`BAT ADC ERR`、`BAT --`、`BAT CHECK x.xxV` の場合は不合格", bringup)

    def test_key_local_console_is_debounced_nonblocking_and_uses_fixed_demo(self) -> None:
        console = (ROOT / "firmware/main/rlcd42_console.c").read_text(encoding="utf-8")
        cmake = (ROOT / "firmware/main/CMakeLists.txt").read_text(encoding="utf-8")

        for token in (
            "RLCD42_KEY_GPIO       GPIO_NUM_18",
            "KEY_POLL_MS           20",
            "KEY_DEBOUNCE_SAMPLES  3",
            "GPIO_PULLUP_ENABLE",
            "pdMS_TO_TICKS(KEY_POLL_MS)",
            "pdMS_TO_TICKS(5)",
            "s_key_seen_released = s_key_stable != 0",
            "if (s_key_seen_released) s_key_pressed = true",
            "*out = SAAN_DEMO_INTERMEDIATE",
            "return SAAN_DEMO_INTERMEDIATE_BYTES",
            "KEY demo ignored while a USB input line is being edited",
        ):
            with self.subTest(token=token):
                self.assertIn(token, console)
        self.assertIn("RLCD42_KEY_GPIO != GPIO_NUM_4", console)
        self.assertIn("now - s_key_last_sample < pdMS_TO_TICKS(KEY_POLL_MS)", console)
        self.assertIn('"rlcd42_console.c"', cmake)
        self.assertNotIn('"${SAAN_MAIN}/saan_console.c"', cmake)

    def test_capability_markers_are_exact_embedded_and_logged(self) -> None:
        expected = {
            "battery": b"RLCD42_CAP:battery-adc1-ch3-x3-v1",
            "key": b"RLCD42_CAP:key-local-demo-v1",
        }
        self.assertEqual(demo.CAPABILITY_MARKERS, expected)

        sources = {
            "battery": (ROOT / "firmware/main/rlcd42_battery.c").read_text(encoding="utf-8"),
            "key": (ROOT / "firmware/main/rlcd42_console.c").read_text(encoding="utf-8"),
        }
        symbols = {"battery": "s_battery_capability", "key": "s_key_capability"}
        for name, marker in expected.items():
            source = sources[name]
            symbol = symbols[name]
            with self.subTest(capability=name):
                self.assertIn(marker.decode("ascii"), source)
                self.assertIn(f"static const char {symbol}[]", source)
                self.assertIn("__attribute__((used))", source)
                self.assertIn(f'ESP_LOGI(TAG, "%s", {symbol})', source)

    def test_built_image_capability_gate_requires_key_only_for_tts_profiles(self) -> None:
        markers = demo.CAPABILITY_MARKERS
        with tempfile.TemporaryDirectory() as temporary:
            image = pathlib.Path(temporary) / "merged.bin"

            image.write_bytes(demo.PROFILE_MARKERS["probe"] + markers["battery"])
            demo.verify_built_capabilities(image, "probe")

            image.write_bytes(
                demo.PROFILE_MARKERS["kana"] + markers["battery"] + markers["key"]
            )
            demo.verify_built_capabilities(image, "kana")

            image.write_bytes(demo.PROFILE_MARKERS["kana"] + markers["battery"])
            with self.assertRaisesRegex(demo.DemoError, "key"):
                demo.verify_built_capabilities(image, "kana")

            image.write_bytes(demo.PROFILE_MARKERS["probe"])
            with self.assertRaisesRegex(demo.DemoError, "battery"):
                demo.verify_built_capabilities(image, "probe")

    def test_audio_codec_readback_gates_pa_and_exact_result_markers(self) -> None:
        audio = (ROOT / "firmware/main/rlcd42_saan_i2s.c").read_text(encoding="utf-8")
        cmake = (ROOT / "firmware/main/CMakeLists.txt").read_text(encoding="utf-8")

        for token in (
            "ES8311_DAC_MUTE_REG   0x31",
            "ES8311_DAC_VOLUME_REG 0x32",
            "ES8311_DAC_MUTE_MASK  0x60",
            "ES8311_VOLUME_ZERO    0x00",
            "esp_codec_dev_read_reg(s_output, ES8311_DAC_VOLUME_REG, &value)",
            "esp_codec_dev_read_reg(s_output, ES8311_DAC_MUTE_REG, &value)",
            'codec_volume_is(ES8311_VOLUME_ZERO, "zero-volume-before-PA")',
            'codec_mute_is(true, "mute-before-PA")',
            'codec_volume_is((uint8_t)(0x56 + volume), "volume-ramp")',
            "i2s_channel_enable(s_tx)",
            "ES8311 MCLK primed before codec reset/config; PA remains LOW",
            "static size_t s_preroll_fill",
            'codec_mute_is(false, "unmute-before-preroll")',
            'codec_volume_is(ES8311_VOLUME_ZERO, "zero-volume-before-PA-off")',
            'codec_mute_is(true, "mute-before-PA-off")',
            "RLCD42_AUDIO_START:OK PA=HIGH VOLUME=%d",
            "RLCD42_AUDIO_START:FAIL PA=LOW",
            "RLCD42_AUDIO_RESULT:OK PA=LOW",
            "RLCD42_AUDIO_RESULT:FAIL PA=LOW_REQUESTED",
            "RLCD42_SILENT_START:OK",
            "RLCD42_SILENT_RESULT:OK PA=COMPILED_OUT",
            "RLCD42_SILENT_RESULT:FAIL PA=COMPILED_OUT",
        ):
            with self.subTest(token=token):
                self.assertIn(token, audio)
        self.assertIn("saan_stream_pull=rlcd42_saan_stream_pull", cmake)
        self.assertIn("const saan_status status = saan_stream_pull(stream, pcm, frames)", audio)
        self.assertIn("if (status != SAAN_OK) s_utterance_transport_ok = false", audio)
        self.assertLess(
            audio.index("i2s_channel_enable(s_tx)"),
            audio.index("es8311_codec_new(&codec_cfg)"),
        )
        self.assertLess(
            audio.index('codec_volume_is(ES8311_VOLUME_ZERO, "zero-volume-before-PA")'),
            audio.index("rlcd42_board_set_amp_enabled(true)"),
        )
        self.assertLess(
            audio.index('codec_mute_is(true, "mute-before-PA-off")'),
            audio.index("rlcd42_board_set_amp_enabled(false)",
                        audio.index('codec_mute_is(true, "mute-before-PA-off")')),
        )

    def test_demo_requires_board_confirmation_before_profile_or_serial_io(self) -> None:
        args = Namespace(
            port="TEST", confirm_board="wrong", profile="kana", silent=False,
            yes_speaker_connected=True, text=None, timeout=1.0,
        )
        with (
            mock.patch.object(demo, "inspect_device") as inspect,
            mock.patch.object(demo, "matching_backup") as backup,
            mock.patch.object(demo, "detect_installed_profile") as detect,
        ):
            with self.assertRaisesRegex(demo.DemoError, "physical board silkscreen"):
                demo.cmd_demo(args)
        inspect.assert_not_called()
        backup.assert_not_called()
        detect.assert_not_called()

    def test_plain_message_requires_kanji_profile_before_device_io(self) -> None:
        args = Namespace(
            port="TEST", confirm_board=demo.BOARD_ID, profile="kana", silent=False,
            yes_speaker_connected=True, text=None, message="おはよう", timeout=1.0,
        )
        with mock.patch.object(demo, "detect_installed_profile") as detect:
            with self.assertRaisesRegex(demo.DemoError, "kanji firmware"):
                demo.cmd_demo(args)
        detect.assert_not_called()

    def test_demo_accepts_only_the_exact_audio_start_and_result_markers(self) -> None:
        args = Namespace(
            port="TEST", confirm_board=demo.BOARD_ID, profile="kana", silent=False,
            yes_speaker_connected=True, text=None, timeout=2.0,
        )
        serial_port = mock.MagicMock()
        serial_port.__enter__.return_value = serial_port
        serial_port.read.side_effect = [
            b"\r\n\xe3\x81\x8b\xe3\x81\xaa> ",
            b"RLCD42_AUDIO_START:OK PA=HIGH VOLUME=100\n",
            b"----- \xe7\xb5\x90\xe6\x9e\x9c -----\n"
            b"RLCD42_AUDIO_RESULT:OK PA=LOW\n\xe3\x81\x8b\xe3\x81\xaa> ",
        ]
        serial_module = types.SimpleNamespace(
            Serial=mock.Mock(return_value=serial_port)
        )
        with (
            mock.patch.object(demo, "inspect_device", return_value=device()),
            mock.patch.object(demo, "matching_backup", return_value=ROOT / "factory.bin"),
            mock.patch.object(demo, "detect_installed_profile", return_value="kana"),
            mock.patch.dict(sys.modules, {"serial": serial_module}),
        ):
            demo.cmd_demo(args)

        writes = b"".join(call.args[0] for call in serial_port.write.call_args_list)
        self.assertIn((demo.DEMO_KANA + "\r\n").encode("utf-8"), writes)

    def test_demo_does_not_accept_generic_result_without_audio_result_marker(self) -> None:
        args = Namespace(
            port="TEST", confirm_board=demo.BOARD_ID, profile="kana", silent=False,
            yes_speaker_connected=True, text=None, timeout=1.0,
        )
        serial_port = mock.MagicMock()
        serial_port.__enter__.return_value = serial_port
        serial_port.read.side_effect = [
            b"\xe3\x81\x8b\xe3\x81\xaa> ",
            b"RLCD42_AUDIO_START:OK PA=HIGH VOLUME=100\n",
            b"----- \xe7\xb5\x90\xe6\x9e\x9c -----\n\xe3\x81\x8b\xe3\x81\xaa> ",
        ]
        serial_module = types.SimpleNamespace(
            Serial=mock.Mock(return_value=serial_port)
        )
        with (
            mock.patch.object(demo, "inspect_device", return_value=device()),
            mock.patch.object(demo, "matching_backup", return_value=ROOT / "factory.bin"),
            mock.patch.object(demo, "detect_installed_profile", return_value="kana"),
            mock.patch.dict(sys.modules, {"serial": serial_module}),
            mock.patch.object(demo.time, "monotonic", side_effect=[0.0, 0.1, 0.2, 2.0]),
        ):
            with self.assertRaisesRegex(demo.DemoError, "result"):
                demo.cmd_demo(args)

    def test_demo_rejects_explicit_audio_failure_result(self) -> None:
        args = Namespace(
            port="TEST", confirm_board=demo.BOARD_ID, profile="kana", silent=False,
            yes_speaker_connected=True, text=None, timeout=2.0,
        )
        serial_port = mock.MagicMock()
        serial_port.__enter__.return_value = serial_port
        serial_port.read.side_effect = [
            b"\xe3\x81\x8b\xe3\x81\xaa> ",
            b"RLCD42_AUDIO_START:OK PA=HIGH VOLUME=100\n",
            b"----- \xe7\xb5\x90\xe6\x9e\x9c -----\n"
            b"RLCD42_AUDIO_RESULT:FAIL PA=LOW_REQUESTED\n\xe3\x81\x8b\xe3\x81\xaa> ",
        ]
        serial_module = types.SimpleNamespace(
            Serial=mock.Mock(return_value=serial_port)
        )
        with (
            mock.patch.object(demo, "inspect_device", return_value=device()),
            mock.patch.object(demo, "matching_backup", return_value=ROOT / "factory.bin"),
            mock.patch.object(demo, "detect_installed_profile", return_value="kana"),
            mock.patch.dict(sys.modules, {"serial": serial_module}),
        ):
            with self.assertRaisesRegex(demo.DemoError, "FAIL|failure"):
                demo.cmd_demo(args)

    def test_silent_demo_requires_its_compiled_out_result_marker(self) -> None:
        args = Namespace(
            port="TEST", confirm_board=demo.BOARD_ID, profile="kana", silent=True,
            yes_speaker_connected=False, text=None, timeout=2.0,
        )
        serial_port = mock.MagicMock()
        serial_port.__enter__.return_value = serial_port
        serial_port.read.side_effect = [
            b"\xe3\x81\x8b\xe3\x81\xaa> ",
            b"RLCD42_SILENT_START:OK\n",
            b"----- \xe7\xb5\x90\xe6\x9e\x9c -----\n"
            b"RLCD42_SILENT_RESULT:OK PA=COMPILED_OUT\n\xe3\x81\x8b\xe3\x81\xaa> ",
        ]
        serial_module = types.SimpleNamespace(
            Serial=mock.Mock(return_value=serial_port)
        )
        with (
            mock.patch.object(demo, "inspect_device", return_value=device()),
            mock.patch.object(demo, "matching_backup", return_value=ROOT / "factory.bin"),
            mock.patch.object(demo, "detect_installed_profile", return_value="kana-silent"),
            mock.patch.dict(sys.modules, {"serial": serial_module}),
        ):
            demo.cmd_demo(args)


if __name__ == "__main__":
    unittest.main()
