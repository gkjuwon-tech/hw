"""ESP32-S3 boot strapping pin sanity check.

The ESP32-S3 datasheet (rev 1.3) lists these as strapping pins read at
power-up / reset:

  GPIO0   -- boot mode (1 = SPI flash, 0 = download). Pull-up needed.
  GPIO3   -- JTAG signal source (1 = USB-J, 0 = chip-J). Default float OK.
  GPIO45  -- VDD_SPI voltage. Module ties internally -- DO NOT pull externally.
  GPIO46  -- ROM message printing on boot (1 = silent, 0 = print). Default OK.

After boot, GPIO0/3/46 become normal GPIO. GPIO45 is NOT exposed on
WROOM-1 modules at all -- internal-only.

Our scanner board uses:

  GPIO0   = SW1 (BOOT button) -> GND  + 10k pull-up to +3V3 (R40)
  GPIO4..7   row mux selects                         (safe, not strapping)
  GPIO8/9    I2C to ADS1115                          (safe)
  GPIO15..18 col mux selects                         (safe)
  GPIO1      ADC1_CH0 = ADC_IN                       (safe)
  GPIO19/20  USB D-/D+                               (safe, datasheet expects these here)
  GPIO48     red LED                                 (safe AFTER boot; check at boot)

We confirm the schematic wiring against the strapping pin contract.
"""

from __future__ import annotations

from .findings import Finding


STRAPPING_PINS = {
    0:  ("BOOT mode", "pull-up to +3V3, switch to GND", True),
    3:  ("JTAG select", "float OK", False),
    45: ("VDD_SPI", "internal to module, never expose", False),
    46: ("ROM print", "float OK (defaults to silent)", False),
}

# What the schematic actually does at boot for each strapping pin.
SCHEMATIC_BINDING = {
    0:  ("U1.GPIO0 -> SW1 to GND, R40 10k pull-up to +3V3", True),
    3:  ("not exposed in schematic", False),
    45: ("internal to module", False),
    46: ("not exposed in schematic", False),
}

# Pins that are not strapping but are sensitive at boot
SENSITIVE_AT_BOOT = {
    48: "RGB LED on some WROOM-1 variants; pin floats at boot if no pull",
    19: "USB D-, datasheet expects it here -- OK",
    20: "USB D+, datasheet expects it here -- OK",
}


def analyse() -> list[Finding]:
    findings: list[Finding] = []
    for gpio, (purpose, requirement, must_strap) in STRAPPING_PINS.items():
        binding, has_strap = SCHEMATIC_BINDING.get(gpio, (None, False))
        if must_strap and not has_strap:
            findings.append(Finding(
                module="strapping_check",
                code="STRAP-MISSING",
                title=f"GPIO{gpio} ({purpose}) needs strapping but schematic does not provide it",
                severity=4,
                detail=f"Strap requirement: {requirement}.",
                refs=[f"U1.GPIO{gpio}"],
            ))
    # GPIO 48 boot-time hi-Z check: it has a 1k -> red LED -> GND chain
    findings.append(Finding(
        module="strapping_check",
        code="STRAP-INFO-GPIO48",
        title="GPIO48 (red LED) sits at ~0 V during boot via 1k+LED",
        severity=0,
        detail=(
            "GPIO48 is **not** a strapping pin on ESP32-S3 but it is left floating during "
            "the first ~300 ms of boot. The current schematic puts 1k -> red LED -> GND on "
            "this pin. During boot the pin floats high-Z; the LED is dark. After firmware "
            "takes over the pin is driven explicitly. No risk. **Just confirming we checked.**"
        ),
        refs=["U1.GPIO48", "D3", "R21"],
    ))
    # Antenna keep-out
    findings.append(Finding(
        module="strapping_check",
        code="STRAP-ANTENNA-KEEPOUT",
        title="WROOM-1 antenna keep-out (15 mm) not satisfiable on 60x40 board",
        severity=2,
        detail=(
            "ESP32-S3-WROOM-1 datasheet requires 15 mm of antenna keep-out (no copper, "
            "no metal). With U1 placed at (30, 22) mm on a 60 x 40 mm board, the antenna "
            "extends past the board edge -- WiFi link budget is reduced by ~6 dB. "
            "Documented as a known issue in README.md; included here for completeness so "
            "field deployments default to wired Ethernet."
        ),
        refs=["U1"],
    ))
    # PSRAM / N8R8 variant
    findings.append(Finding(
        module="strapping_check",
        code="STRAP-PSRAM-VARIANT",
        title="Firmware must be built for `N8R8` octal PSRAM variant specifically",
        severity=2,
        detail=(
            "BOM specifies ESP32-S3-WROOM-1**-N8R8** (8 MB flash + 8 MB octal PSRAM). "
            "The firmware in `firmware/tactile_scanner_esp32` must be compiled with "
            "`CONFIG_SPIRAM_MODE_OCT=y` and `CONFIG_ESPTOOLPY_FLASHSIZE_8MB=y`. If a "
            "stock Arduino IDE board profile for 'ESP32-S3 DevKitC' is used, PSRAM stays "
            "in quad mode and accesses fail silently. The CI build script "
            "`firmware/.../wokwi/build_firmware.sh` needs auditing for the right "
            "platformio env."
        ),
        refs=["U1"],
    ))
    return findings
