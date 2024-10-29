# Changelog

## [0.7.6](https://github.com/python-kasa/python-kasa/tree/0.7.6) (2024-10-29)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.7.5...0.7.6)

**Release summary:**

- Experimental support for Tapo cameras and the Tapo H200 hub which uses the same protocol.
- Better timestamp support across all devices.
- Support for new devices P304M, S200D and S200B (see README.md for note on the S200 support).
- Various other fixes and minor features.

**Implemented enhancements:**

- Add support for setting the timezone [\#436](https://github.com/python-kasa/python-kasa/issues/436)
- Add stream\_rtsp\_url to camera module [\#1197](https://github.com/python-kasa/python-kasa/pull/1197) (@sdb9696)
- Try default logon credentials in SslAesTransport [\#1195](https://github.com/python-kasa/python-kasa/pull/1195) (@sdb9696)
- Allow enabling experimental devices from environment variable [\#1194](https://github.com/python-kasa/python-kasa/pull/1194) (@sdb9696)
- Add core device, child and camera modules to smartcamera [\#1193](https://github.com/python-kasa/python-kasa/pull/1193) (@sdb9696)
- Fallback to get\_current\_power if get\_energy\_usage does not provide current\_power [\#1186](https://github.com/python-kasa/python-kasa/pull/1186) (@Fulch36)
- Add https parameter to device class factory [\#1184](https://github.com/python-kasa/python-kasa/pull/1184) (@sdb9696)
- Add discovery list command to cli [\#1183](https://github.com/python-kasa/python-kasa/pull/1183) (@sdb9696)
- Add Time module to SmartCamera devices [\#1182](https://github.com/python-kasa/python-kasa/pull/1182) (@sdb9696)
- Add try\_connect\_all to allow initialisation without udp broadcast [\#1171](https://github.com/python-kasa/python-kasa/pull/1171) (@sdb9696)
- Update dump\_devinfo for smart camera protocol [\#1169](https://github.com/python-kasa/python-kasa/pull/1169) (@sdb9696)
- Enable newer encrypted discovery protocol [\#1168](https://github.com/python-kasa/python-kasa/pull/1168) (@sdb9696)
- Initial TapoCamera support [\#1165](https://github.com/python-kasa/python-kasa/pull/1165) (@sdb9696)
- Add waterleak alert timestamp [\#1162](https://github.com/python-kasa/python-kasa/pull/1162) (@rytilahti)
- Create common Time module and add time set cli command [\#1157](https://github.com/python-kasa/python-kasa/pull/1157) (@sdb9696)

**Fixed bugs:**

- Only send 20002 discovery request with key included [\#1207](https://github.com/python-kasa/python-kasa/pull/1207) (@sdb9696)
- Fix SslAesTransport default login and add tests [\#1202](https://github.com/python-kasa/python-kasa/pull/1202) (@sdb9696)
- Fix device\_config serialisation of https value [\#1196](https://github.com/python-kasa/python-kasa/pull/1196) (@sdb9696)

**Added support for devices:**

- Add S200B\(EU\) fw 1.11.0 fixture [\#1205](https://github.com/python-kasa/python-kasa/pull/1205) (@sdb9696)
- Add TC65 fixture [\#1200](https://github.com/python-kasa/python-kasa/pull/1200) (@rytilahti)
- Add P304M\(UK\) test fixture [\#1185](https://github.com/python-kasa/python-kasa/pull/1185) (@Fulch36)
- Add H200 experimental fixture [\#1180](https://github.com/python-kasa/python-kasa/pull/1180) (@sdb9696)
- Add S200D button fixtures [\#1161](https://github.com/python-kasa/python-kasa/pull/1161) (@rytilahti)

**Project maintenance:**

- Fix mypy errors in parse_pcap_klap [\#1214](https://github.com/python-kasa/python-kasa/pull/1214) (@sdb9696)
- Make HSV NamedTuple creation more efficient [\#1211](https://github.com/python-kasa/python-kasa/pull/1211) (@sdb9696)
- dump\_devinfo: query get\_current\_brt for iot dimmers [\#1209](https://github.com/python-kasa/python-kasa/pull/1209) (@rytilahti)
- Add trigger\_logs and double\_click to dump\_devinfo helper [\#1208](https://github.com/python-kasa/python-kasa/pull/1208) (@sdb9696)
- Fix smartcamera childdevice module [\#1206](https://github.com/python-kasa/python-kasa/pull/1206) (@sdb9696)
- Add H200\(EU\) fw 1.3.2 fixture [\#1204](https://github.com/python-kasa/python-kasa/pull/1204) (@sdb9696)
- Do not pass None as timeout to http requests [\#1203](https://github.com/python-kasa/python-kasa/pull/1203) (@sdb9696)
- Update SMART test framework to use fake child protocols [\#1199](https://github.com/python-kasa/python-kasa/pull/1199) (@sdb9696)
- Allow passing an aiohttp client session during discover try\_connect\_all [\#1198](https://github.com/python-kasa/python-kasa/pull/1198) (@sdb9696)
- Add test framework for smartcamera [\#1192](https://github.com/python-kasa/python-kasa/pull/1192) (@sdb9696)
- Rename experimental fixtures folder to smartcamera [\#1191](https://github.com/python-kasa/python-kasa/pull/1191) (@sdb9696)
- Combine smartcamera error codes into SmartErrorCode [\#1190](https://github.com/python-kasa/python-kasa/pull/1190) (@sdb9696)
- Allow deriving from SmartModule without being registered [\#1189](https://github.com/python-kasa/python-kasa/pull/1189) (@sdb9696)
- Improve supported module checks for hub children [\#1188](https://github.com/python-kasa/python-kasa/pull/1188) (@sdb9696)
- Update smartcamera to support single get/set/do requests [\#1187](https://github.com/python-kasa/python-kasa/pull/1187) (@sdb9696)
- Add S200B\(US\) fw 1.12.0 fixture [\#1181](https://github.com/python-kasa/python-kasa/pull/1181) (@sdb9696)
- Add T110\(US\), T310\(US\) and T315\(US\) sensor fixtures [\#1179](https://github.com/python-kasa/python-kasa/pull/1179) (@sdb9696)
- Enforce EOLs for \*.rst and \*.md [\#1178](https://github.com/python-kasa/python-kasa/pull/1178) (@rytilahti)
- Convert fixtures to use unix newlines [\#1177](https://github.com/python-kasa/python-kasa/pull/1177) (@rytilahti)
- Add motion sensor to known categories [\#1176](https://github.com/python-kasa/python-kasa/pull/1176) (@rytilahti)
- Drop urllib3 dependency and create ssl context in executor thread [\#1175](https://github.com/python-kasa/python-kasa/pull/1175) (@sdb9696)
- Expose smart child device map as a class constant [\#1173](https://github.com/python-kasa/python-kasa/pull/1173) (@sdb9696)

## [0.7.5](https://github.com/python-kasa/python-kasa/tree/0.7.5) (2024-10-08)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.7.4...0.7.5)

**Release summary:**

- Fix for KP303 on Firmware 1.0.6
- Fix for `on_since` value jitter
- Various maintenance items

**Breaking changes:**

- Make iot time timezone aware [\#1147](https://github.com/python-kasa/python-kasa/pull/1147) (@sdb9696)

**Fixed bugs:**

- Send empty dictionary instead of null for iot queries [\#1145](https://github.com/python-kasa/python-kasa/pull/1145) (@sdb9696)
- parse\_pcap\_klap: require source host [\#1137](https://github.com/python-kasa/python-kasa/pull/1137) (@rytilahti)
- parse\_pcap\_klap: use request\_uri for matching the response [\#1136](https://github.com/python-kasa/python-kasa/pull/1136) (@rytilahti)
- Use tzinfo in time constructor instead of astime for iot devices [\#1158](https://github.com/python-kasa/python-kasa/pull/1158) (@sdb9696)
- Stabilise on\_since value for smart devices [\#1144](https://github.com/python-kasa/python-kasa/pull/1144) (@sdb9696)

**Project maintenance:**

- Move feature initialization from \_\_init\_\_ to \_initialize\_features [\#1140](https://github.com/python-kasa/python-kasa/pull/1140) (@rytilahti)
- Cache zoneinfo for smart devices [\#1156](https://github.com/python-kasa/python-kasa/pull/1156) (@sdb9696)
- Correctly define SmartModule.call as an async function [\#1148](https://github.com/python-kasa/python-kasa/pull/1148) (@sdb9696)
- Remove async magic patch from tests [\#1146](https://github.com/python-kasa/python-kasa/pull/1146) (@sdb9696)

**Closed issues:**

- Move code examples out from docs [\#630](https://github.com/python-kasa/python-kasa/issues/630)

## [0.7.4](https://github.com/python-kasa/python-kasa/tree/0.7.4) (2024-09-27)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.7.3...0.7.4)

**Release summary:**

- KL135 color temp range corrected to 9000k max
- Minor enhancements and project maintenance

**Implemented enhancements:**

- Add factory\_reset\(\) to iotdevice [\#1125](https://github.com/python-kasa/python-kasa/pull/1125) (@rytilahti)
- Add reboot\(\) to the device interface [\#1124](https://github.com/python-kasa/python-kasa/pull/1124) (@rytilahti)
- Add factory-reset command to cli [\#1108](https://github.com/python-kasa/python-kasa/pull/1108) (@rytilahti)

**Fixed bugs:**

- Extend KL135 ct range up to 9000K [\#1123](https://github.com/python-kasa/python-kasa/pull/1123) (@rytilahti)
- Fix cli command for device off [\#1121](https://github.com/python-kasa/python-kasa/pull/1121) (@sdb9696)

**Project maintenance:**

- Use pytest-socket to ensure no tests are performing io [\#1133](https://github.com/python-kasa/python-kasa/pull/1133) (@sdb9696)
- Enable ruff lint pycodestyle warnings [\#1132](https://github.com/python-kasa/python-kasa/pull/1132) (@sdb9696)
- Add autouse fixture to patch asyncio.sleep [\#1131](https://github.com/python-kasa/python-kasa/pull/1131) (@sdb9696)
- Mock asyncio.sleep for klapprotocol tests [\#1130](https://github.com/python-kasa/python-kasa/pull/1130) (@rytilahti)
- Add fixture for T110 fw 1.9.0 [\#1129](https://github.com/python-kasa/python-kasa/pull/1129) (@rytilahti)
- Speed up and simplify github workflows [\#1128](https://github.com/python-kasa/python-kasa/pull/1128) (@sdb9696)
- Add KS200M\(US\) fw 1.0.12 fixture [\#1127](https://github.com/python-kasa/python-kasa/pull/1127) (@GatorEG)
- Add stale PR/Issue github workflow [\#1126](https://github.com/python-kasa/python-kasa/pull/1126) (@sdb9696)
- Add fixture for KL135\(US\) fw 1.0.15 [\#1122](https://github.com/python-kasa/python-kasa/pull/1122) (@rytilahti)

## [0.7.3](https://github.com/python-kasa/python-kasa/tree/0.7.3) (2024-09-10)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.7.2...0.7.3)

**Release summary:**

- Migrate from `poetry` to `uv` for package/project management.
- Various minor code improvements

**Project maintenance:**

- Do not regenerate aes key pair [\#1114](https://github.com/python-kasa/python-kasa/pull/1114) (@sdb9696)
- Fix tests due to yarl URL str output change [\#1112](https://github.com/python-kasa/python-kasa/pull/1112) (@sdb9696)
- Add missing type hints to alarm module [\#1111](https://github.com/python-kasa/python-kasa/pull/1111) (@rytilahti)
- Add KH100 EU fixtures [\#1109](https://github.com/python-kasa/python-kasa/pull/1109) (@rytilahti)
- Migrate from poetry to uv for dependency and package management [\#986](https://github.com/python-kasa/python-kasa/pull/986) (@sdb9696)

## [0.7.2](https://github.com/python-kasa/python-kasa/tree/0.7.2) (2024-08-30)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.7.1...0.7.2)

**Release summary:**

- **Breaking** change to disable including the check for the latest firmware for tapo devices and newer kasa devices in the standard update cycle. To check for the latest firmware call `check_latest_firmware` on the firmware module or run the `check_latest_firmware` feature.
- Minor bugfixes and improvements.

**Breaking changes:**

- Disable automatic updating of latest firmware [\#1103](https://github.com/python-kasa/python-kasa/pull/1103) (@sdb9696)

**Implemented enhancements:**

- Improve performance of dict merge code [\#1097](https://github.com/python-kasa/python-kasa/pull/1097) (@bdraco)

**Fixed bugs:**

- Fix logging in iotdevice when a module is module not supported [\#1100](https://github.com/python-kasa/python-kasa/pull/1100) (@bdraco)

**Documentation updates:**

- Fix incorrect docs link in contributing.md [\#1099](https://github.com/python-kasa/python-kasa/pull/1099) (@sdb9696)

**Project maintenance:**

- Remove top level await xdoctest fixture [\#1098](https://github.com/python-kasa/python-kasa/pull/1098) (@sdb9696)
- Enable python 3.13, allow pre-releases for CI [\#1086](https://github.com/python-kasa/python-kasa/pull/1086) (@rytilahti)
- Add flake8-pytest-style \(PT\) for ruff [\#1105](https://github.com/python-kasa/python-kasa/pull/1105) (@rytilahti)
- Add flake8-logging \(LOG\) and flake8-logging-format \(G\) for ruff [\#1104](https://github.com/python-kasa/python-kasa/pull/1104) (@rytilahti)
- Add missing typing\_extensions dependency [\#1101](https://github.com/python-kasa/python-kasa/pull/1101) (@sdb9696)

## [0.7.1](https://github.com/python-kasa/python-kasa/tree/0.7.1) (2024-07-31)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.7.0.5...0.7.1)

**Release highlights:**
- This release consists mainly of bugfixes and project improvements.
- There is also new support for Tapo T100 motion sensors.
- The CLI now supports child devices on all applicable commands.

**Implemented enhancements:**

- Expose reboot action [\#1073](https://github.com/python-kasa/python-kasa/pull/1073) (@rytilahti)
- Decrypt KLAP data from PCAP files [\#1041](https://github.com/python-kasa/python-kasa/pull/1041) (@clstrickland)
- Support child devices in all applicable cli commands [\#1020](https://github.com/python-kasa/python-kasa/pull/1020) (@sdb9696)

**Fixed bugs:**

- Error connecting to L920-5 Smart LED Strip [\#1040](https://github.com/python-kasa/python-kasa/issues/1040)
- Handle module errors more robustly and add query params to light preset and transition [\#1036](https://github.com/python-kasa/python-kasa/pull/1036) (@sdb9696)
- Fix iot light effect brightness [\#1092](https://github.com/python-kasa/python-kasa/pull/1092) (@sdb9696)
- Enable setting brightness with color temp for smart devices [\#1091](https://github.com/python-kasa/python-kasa/pull/1091) (@sdb9696)
- Do not send light\_on value to iot bulb set\_state [\#1090](https://github.com/python-kasa/python-kasa/pull/1090) (@sdb9696)
- Allow erroring modules to recover [\#1080](https://github.com/python-kasa/python-kasa/pull/1080) (@sdb9696)
- Raise KasaException on decryption errors [\#1078](https://github.com/python-kasa/python-kasa/pull/1078) (@sdb9696)
- Update smart request parameter handling [\#1061](https://github.com/python-kasa/python-kasa/pull/1061) (@sdb9696)
- Fix light preset module when list contains lighting effects [\#1048](https://github.com/python-kasa/python-kasa/pull/1048) (@sdb9696)
- Fix credential hash to return None on empty credentials [\#1029](https://github.com/python-kasa/python-kasa/pull/1029) (@sdb9696)

**Added support for devices:**

- Add support for T100 motion sensor [\#1079](https://github.com/python-kasa/python-kasa/pull/1079) (@rytilahti)

**Project maintenance:**

- Bump project version to 0.7.0.5 [\#1087](https://github.com/python-kasa/python-kasa/pull/1087) (@sdb9696)
- Add KP400\(US\) v1.0.4 fixture [\#1051](https://github.com/python-kasa/python-kasa/pull/1051) (@gimpy88)
- Add new HS220 kasa aes fixture [\#1050](https://github.com/python-kasa/python-kasa/pull/1050) (@sdb9696)
- Add KS205\(US\) v1.1.0 fixture [\#1049](https://github.com/python-kasa/python-kasa/pull/1049) (@gimpy88)
- Fix generate\_supported pre commit to run in venv [\#1085](https://github.com/python-kasa/python-kasa/pull/1085) (@sdb9696)
- Fix intermittently failing decryption error test [\#1082](https://github.com/python-kasa/python-kasa/pull/1082) (@sdb9696)
- Fix mypy pre-commit hook on windows [\#1081](https://github.com/python-kasa/python-kasa/pull/1081) (@sdb9696)
- Update RELEASING.md for patch releases [\#1076](https://github.com/python-kasa/python-kasa/pull/1076) (@sdb9696)
- Use monotonic time for query timing [\#1070](https://github.com/python-kasa/python-kasa/pull/1070) (@sdb9696)
- Fix parse\_pcap\_klap on windows and support default credentials [\#1068](https://github.com/python-kasa/python-kasa/pull/1068) (@sdb9696)
- Add fixture file for KP405 fw 1.0.6 [\#1063](https://github.com/python-kasa/python-kasa/pull/1063) (@daleye)
- Bump project version to 0.7.0.3 [\#1053](https://github.com/python-kasa/python-kasa/pull/1053) (@sdb9696)
- Add KS200M\(US\) v1.0.11 fixture [\#1047](https://github.com/python-kasa/python-kasa/pull/1047) (@sdb9696)
- Add KS225\(US\) v1.1.0 fixture [\#1046](https://github.com/python-kasa/python-kasa/pull/1046) (@sdb9696)
- Split out main cli module into lazily loaded submodules [\#1039](https://github.com/python-kasa/python-kasa/pull/1039) (@sdb9696)
- Structure cli into a package [\#1038](https://github.com/python-kasa/python-kasa/pull/1038) (@sdb9696)
- Add KP400 v1.0.3 fixture [\#1037](https://github.com/python-kasa/python-kasa/pull/1037) (@gimpy88)
- Add L920\(EU\) v1.1.3 fixture [\#1031](https://github.com/python-kasa/python-kasa/pull/1031) (@rytilahti)
- Update changelog generator config [\#1030](https://github.com/python-kasa/python-kasa/pull/1030) (@sdb9696)

## [0.7.0.5](https://github.com/python-kasa/python-kasa/tree/0.7.0.5) (2024-07-18)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.7.0.4...0.7.0.5)

A critical bugfix for an issue with some L530 Series devices and a redactor for sensitive info from debug logs.

**Fixed bugs:**

- Only refresh smart LightEffect module daily [\#1064](https://github.com/python-kasa/python-kasa/pull/1064) (@sdb9696)

**Project maintenance:**

- Redact sensitive info from debug logs [\#1069](https://github.com/python-kasa/python-kasa/pull/1069) (@sdb9696)

## [0.7.0.4](https://github.com/python-kasa/python-kasa/tree/0.7.0.4) (2024-07-11)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.7.0.3...0.7.0.4)

Critical bugfixes for issues with P100s and thermostats


**Fixed bugs:**

- Use first known thermostat state as main state \(pick \#1054\) [\#1057](https://github.com/python-kasa/python-kasa/pull/1057) (@sdb9696)
- Defer module updates for less volatile modules \(pick 1052\) [\#1056](https://github.com/python-kasa/python-kasa/pull/1056) (@sdb9696)
- Use first known thermostat state as main state [\#1054](https://github.com/python-kasa/python-kasa/pull/1054) (@rytilahti)
- Defer module updates for less volatile modules [\#1052](https://github.com/python-kasa/python-kasa/pull/1052) (@sdb9696)

## [0.7.0.3](https://github.com/python-kasa/python-kasa/tree/0.7.0.3) (2024-07-04)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.7.0.2...0.7.0.3)

Critical bugfix for issue #1033 with ks225 and S505D light preset module errors.
Partially fixes light preset module errors with L920 and L930.

**Fixed bugs:**

- Handle module errors more robustly and add query params to light preset and transition [\#1043](https://github.com/python-kasa/python-kasa/pull/1043) (@sdb9696)

**Documentation updates:**

- Misleading usage of asyncio.run\(\) in code examples [\#348](https://github.com/python-kasa/python-kasa/issues/348)

**Project maintenance:**

- Enable CI on the patch branch [\#1042](https://github.com/python-kasa/python-kasa/pull/1042) (@sdb9696)

## [0.7.0.2](https://github.com/python-kasa/python-kasa/tree/0.7.0.2) (2024-07-01)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.7.0.1...0.7.0.2)

This patch release fixes some minor issues found out during testing against all new homeassistant platforms.

**Fixed bugs:**

- Disable multi-request on unknown errors [\#1027](https://github.com/python-kasa/python-kasa/pull/1027) (@sdb9696)
- Disable multi requests on json decode error during multi-request [\#1025](https://github.com/python-kasa/python-kasa/pull/1025) (@sdb9696)
- Fix changing brightness when effect is active [\#1019](https://github.com/python-kasa/python-kasa/pull/1019) (@rytilahti)
- Update light transition module to work with child devices [\#1017](https://github.com/python-kasa/python-kasa/pull/1017) (@sdb9696)
- Handle unknown error codes gracefully [\#1016](https://github.com/python-kasa/python-kasa/pull/1016) (@rytilahti)

**Project maintenance:**

- Make parent attribute on device consistent across iot and smart [\#1023](https://github.com/python-kasa/python-kasa/pull/1023) (@sdb9696)
- Cache SmartErrorCode creation [\#1022](https://github.com/python-kasa/python-kasa/pull/1022) (@bdraco)

## [0.7.0.1](https://github.com/python-kasa/python-kasa/tree/0.7.0.1) (2024-06-25)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.7.0...0.7.0.1)

This patch release fixes some minor issues found out during testing against all new homeassistant platforms.

**Fixed bugs:**

- Disable lighttransition module on child devices [\#1013](https://github.com/python-kasa/python-kasa/pull/1013) (@sdb9696)
- Fix post update hook for iot child devices [\#1011](https://github.com/python-kasa/python-kasa/pull/1011) (@sdb9696)
- Fix iot strip so the children do not have led and cloud modules [\#1010](https://github.com/python-kasa/python-kasa/pull/1010) (@sdb9696)
- Require explicit feature type [\#1006](https://github.com/python-kasa/python-kasa/pull/1006) (@rytilahti)

**Merged pull requests:**

- Remove frost\_protection feature [\#1009](https://github.com/python-kasa/python-kasa/pull/1009) (@rytilahti)

## [0.7.0](https://github.com/python-kasa/python-kasa/tree/0.7.0) (2024-06-23)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.6.2.1...0.7.0)

We have been working hard behind the scenes to make this major release possible.
This release brings a major refactoring of the library to serve the ever-growing list of supported devices and paves the way for the future, yet unsupported devices.
The library now exposes device features through generic module and feature interfaces, that allows easy extension for future improvements.

With almost 180 merged pull requests, over 200 changed files and  since the last release, this release includes lots of goodies for everyone:
* Support for multi-functional devices like the dimmable fan KS240.
* Initial support for hubs and hub-connected devices like thermostats and sensors.
* Both IOT (legacy kasa) and SMART (tapo and newer kasa) devices now expose features and share common API.
* Modules to allow controlling new devices and functions such as light presets, fan controls, thermostats, humidity sensors, firmware updates and alarms.
* The common APIs allow dynamic introspection of available device features, making it easy to create dynamic interfaces.
* Improved documentation.

Hope you enjoy the release, feel free to leave a comment and feedback!

If you have a device that works, but is not listed in our supported devices list, feel free to [contribute fixture files](https://python-kasa.readthedocs.io/en/latest/contribute.html#contributing-fixture-files) to help us to make the library even better!

> git diff 0.6.2.1..HEAD|diffstat
> 214 files changed, 26960 insertions(+), 6310 deletions(-)

For more information on the changes please checkout our [documentation on the API changes](https://python-kasa.readthedocs.io/en/latest/deprecated.html)

**Breaking changes:**

- Add common energy module and deprecate device emeter attributes [\#976](https://github.com/python-kasa/python-kasa/pull/976) (@sdb9696)
- Move SmartBulb into SmartDevice [\#874](https://github.com/python-kasa/python-kasa/pull/874) (@sdb9696)
- Change state\_information to return feature values [\#804](https://github.com/python-kasa/python-kasa/pull/804) (@rytilahti)
- Remove SmartPlug in favor of SmartDevice [\#781](https://github.com/python-kasa/python-kasa/pull/781) (@rytilahti)
- Add generic interface for accessing device features [\#741](https://github.com/python-kasa/python-kasa/pull/741) (@rytilahti)

**Implemented enhancements:**

- Radiator support \(KE100\) [\#422](https://github.com/python-kasa/python-kasa/issues/422)
- Cleanup cli output [\#1000](https://github.com/python-kasa/python-kasa/pull/1000) (@rytilahti)
- Update mode, time, rssi and report\_interval feature names/units [\#995](https://github.com/python-kasa/python-kasa/pull/995) (@sdb9696)
- Add timezone to on\_since attributes [\#978](https://github.com/python-kasa/python-kasa/pull/978) (@sdb9696)
- Add type hints to feature set\_value [\#974](https://github.com/python-kasa/python-kasa/pull/974) (@sdb9696)
- Handle unknown light effect names and only calculate effect list once [\#973](https://github.com/python-kasa/python-kasa/pull/973) (@sdb9696)
- Support smart child modules queries [\#967](https://github.com/python-kasa/python-kasa/pull/967) (@sdb9696)
- Do not expose child modules on parent devices [\#964](https://github.com/python-kasa/python-kasa/pull/964) (@sdb9696)
- Do not add parent only modules to strip sockets [\#963](https://github.com/python-kasa/python-kasa/pull/963) (@sdb9696)
- Make device initialisation easier by reducing required imports [\#936](https://github.com/python-kasa/python-kasa/pull/936) (@sdb9696)
- Fix set\_state for common light modules [\#929](https://github.com/python-kasa/python-kasa/pull/929) (@sdb9696)
- Add state feature for iot devices [\#924](https://github.com/python-kasa/python-kasa/pull/924) (@rytilahti)
- Add post update hook to module and use in smart LightEffect [\#921](https://github.com/python-kasa/python-kasa/pull/921) (@sdb9696)
- Add LightEffect module for smart light strips [\#918](https://github.com/python-kasa/python-kasa/pull/918) (@sdb9696)
- Improve categorization of features [\#904](https://github.com/python-kasa/python-kasa/pull/904) (@rytilahti)
- Make get\_module return typed module [\#892](https://github.com/python-kasa/python-kasa/pull/892) (@sdb9696)
- Add LightEffectModule for dynamic light effects on SMART bulbs [\#887](https://github.com/python-kasa/python-kasa/pull/887) (@sdb9696)
- Implement choice feature type [\#880](https://github.com/python-kasa/python-kasa/pull/880) (@rytilahti)
- Add Fan interface for SMART devices [\#873](https://github.com/python-kasa/python-kasa/pull/873) (@sdb9696)
- Improve temperature controls [\#872](https://github.com/python-kasa/python-kasa/pull/872) (@rytilahti)
- Add precision\_hint to feature [\#871](https://github.com/python-kasa/python-kasa/pull/871) (@rytilahti)
- Be more lax on unknown SMART devices [\#863](https://github.com/python-kasa/python-kasa/pull/863) (@rytilahti)
- Handle paging of partial responses of lists like child\_device\_info [\#862](https://github.com/python-kasa/python-kasa/pull/862) (@sdb9696)
- Better firmware module support for devices not connected to the internet [\#854](https://github.com/python-kasa/python-kasa/pull/854) (@sdb9696)
- Re-query missing responses after multi request errors [\#850](https://github.com/python-kasa/python-kasa/pull/850) (@sdb9696)
- Implement action feature [\#849](https://github.com/python-kasa/python-kasa/pull/849) (@rytilahti)
- Add temperature control module for smart [\#848](https://github.com/python-kasa/python-kasa/pull/848) (@rytilahti)
- Implement feature categories [\#846](https://github.com/python-kasa/python-kasa/pull/846) (@rytilahti)
- Expose IOT emeter info as features [\#844](https://github.com/python-kasa/python-kasa/pull/844) (@rytilahti)
- Add support for feature units [\#843](https://github.com/python-kasa/python-kasa/pull/843) (@rytilahti)
- Add ColorModule for smart devices [\#840](https://github.com/python-kasa/python-kasa/pull/840) (@sdb9696)
- Add colortemp feature for iot devices [\#827](https://github.com/python-kasa/python-kasa/pull/827) (@rytilahti)
- Add support for firmware module v1 [\#821](https://github.com/python-kasa/python-kasa/pull/821) (@sdb9696)
- Add colortemp module [\#814](https://github.com/python-kasa/python-kasa/pull/814) (@rytilahti)
- Add iot brightness feature [\#808](https://github.com/python-kasa/python-kasa/pull/808) (@sdb9696)
- Revise device initialization and subsequent updates [\#807](https://github.com/python-kasa/python-kasa/pull/807) (@rytilahti)
- Add brightness module [\#806](https://github.com/python-kasa/python-kasa/pull/806) (@rytilahti)
- Support multiple child requests [\#795](https://github.com/python-kasa/python-kasa/pull/795) (@sdb9696)
- Support for on\_off\_gradually v2+ [\#793](https://github.com/python-kasa/python-kasa/pull/793) (@rytilahti)
- Improve smartdevice update module [\#791](https://github.com/python-kasa/python-kasa/pull/791) (@rytilahti)
- Add --child option to feature command [\#789](https://github.com/python-kasa/python-kasa/pull/789) (@rytilahti)
- Add temperature\_unit feature to t315 [\#788](https://github.com/python-kasa/python-kasa/pull/788) (@rytilahti)
- Add feature for ambient light sensor [\#787](https://github.com/python-kasa/python-kasa/pull/787) (@shifty35)
- Improve autooff name and unit [\#997](https://github.com/python-kasa/python-kasa/pull/997) (@rytilahti)
- Add unit\_getter for feature [\#993](https://github.com/python-kasa/python-kasa/pull/993) (@rytilahti)
- Add time sync command [\#951](https://github.com/python-kasa/python-kasa/pull/951) (@rytilahti)
- Add light presets common module to devices. [\#907](https://github.com/python-kasa/python-kasa/pull/907) (@sdb9696)
- Create common interfaces for remaining device types [\#895](https://github.com/python-kasa/python-kasa/pull/895) (@sdb9696)
- Add initial support for H100 and T315 [\#776](https://github.com/python-kasa/python-kasa/pull/776) (@rytilahti)
- Generalize smartdevice child support [\#775](https://github.com/python-kasa/python-kasa/pull/775) (@rytilahti)
- Raise CLI errors in debug mode [\#771](https://github.com/python-kasa/python-kasa/pull/771) (@sdb9696)
- Add cloud module for smartdevice [\#767](https://github.com/python-kasa/python-kasa/pull/767) (@rytilahti)
- Add firmware module for smartdevice [\#766](https://github.com/python-kasa/python-kasa/pull/766) (@rytilahti)
- Add fan module [\#764](https://github.com/python-kasa/python-kasa/pull/764) (@rytilahti)
- Add smartdevice module for led controls [\#761](https://github.com/python-kasa/python-kasa/pull/761) (@rytilahti)
- Auto auto-off module for smartdevice [\#760](https://github.com/python-kasa/python-kasa/pull/760) (@rytilahti)
- Add smartdevice module for smooth transitions [\#759](https://github.com/python-kasa/python-kasa/pull/759) (@rytilahti)
- Initial implementation for modularized smartdevice [\#757](https://github.com/python-kasa/python-kasa/pull/757) (@rytilahti)
- Let caller handle SMART errors on multi-requests [\#754](https://github.com/python-kasa/python-kasa/pull/754) (@sdb9696)
- Add 'shell' command to cli [\#738](https://github.com/python-kasa/python-kasa/pull/738) (@rytilahti)

**Fixed bugs:**

- TAPO P100 \(hw 1.0.0, sw 1.1.3\) EU plug with 0.6.2.1 Kasa results JSON\_DECODE\_FAIL\_ERROR [\#819](https://github.com/python-kasa/python-kasa/issues/819)
- Cannot add Tapo Plug P110 to Home Assistant 2024.2.3 - Error in debug mode [\#797](https://github.com/python-kasa/python-kasa/issues/797)
- KS240 gets discovered but will not authenticate [\#749](https://github.com/python-kasa/python-kasa/issues/749)
- Individual commands do not work on discovered devices [\#71](https://github.com/python-kasa/python-kasa/issues/71)
- SMART.TAPOHUB does not work with 0.7.0 dev2 [\#958](https://github.com/python-kasa/python-kasa/issues/958)
- Fix --help on subcommands [\#885](https://github.com/python-kasa/python-kasa/issues/885)
- "Unclosed client session" Trying to set brightness on Tapo Bulb [\#828](https://github.com/python-kasa/python-kasa/issues/828)
- Error when trying to discover new Tapo P110 plug [\#818](https://github.com/python-kasa/python-kasa/issues/818)
- Individual errors cause failing the whole query  [\#616](https://github.com/python-kasa/python-kasa/issues/616)
- Fix smart led status to report rule status [\#1002](https://github.com/python-kasa/python-kasa/pull/1002) (@sdb9696)
- Demote device\_time back to debug [\#1001](https://github.com/python-kasa/python-kasa/pull/1001) (@rytilahti)
- Add supported check to light transition module [\#971](https://github.com/python-kasa/python-kasa/pull/971) (@sdb9696)
- Fix switching off light effects for iot lights strips [\#961](https://github.com/python-kasa/python-kasa/pull/961) (@sdb9696)
- Add state features to iot strip sockets [\#960](https://github.com/python-kasa/python-kasa/pull/960) (@sdb9696)
- Ensure http delay logic works during default login attempt [\#959](https://github.com/python-kasa/python-kasa/pull/959) (@sdb9696)
- Fix fan speed level when off and derive smart fan module from common fan interface [\#957](https://github.com/python-kasa/python-kasa/pull/957) (@sdb9696)
- Do not show a zero error code when cli exits from showing help [\#935](https://github.com/python-kasa/python-kasa/pull/935) (@rytilahti)
- Initialize autooff features only when data is available [\#933](https://github.com/python-kasa/python-kasa/pull/933) (@rytilahti)
- Fix potential infinite loop if incomplete lists returned [\#920](https://github.com/python-kasa/python-kasa/pull/920) (@sdb9696)
- Add 'battery\_percentage' only when it's available [\#906](https://github.com/python-kasa/python-kasa/pull/906) (@rytilahti)
- Add missing alarm volume 'normal' [\#899](https://github.com/python-kasa/python-kasa/pull/899) (@rytilahti)
- Use Path.save for saving the fixtures [\#894](https://github.com/python-kasa/python-kasa/pull/894) (@rytilahti)
- Fix wifi scan re-querying error [\#891](https://github.com/python-kasa/python-kasa/pull/891) (@sdb9696)
- Fix --help on subcommands [\#886](https://github.com/python-kasa/python-kasa/pull/886) (@rytilahti)
- Fix smartprotocol response list handler to handle null reponses [\#884](https://github.com/python-kasa/python-kasa/pull/884) (@sdb9696)
- Improve feature setter robustness [\#870](https://github.com/python-kasa/python-kasa/pull/870) (@rytilahti)
- smartbulb: Limit brightness range to 1-100 [\#829](https://github.com/python-kasa/python-kasa/pull/829) (@rytilahti)
- Fix energy module calling get\_current\_power [\#798](https://github.com/python-kasa/python-kasa/pull/798) (@sdb9696)
- Fix auto update switch [\#786](https://github.com/python-kasa/python-kasa/pull/786) (@rytilahti)
- Fix to call update when only --device-family passed to cli [\#987](https://github.com/python-kasa/python-kasa/pull/987) (@sdb9696)
- Disallow non-targeted device commands [\#982](https://github.com/python-kasa/python-kasa/pull/982) (@rytilahti)
- Require update in cli for wifi commands [\#956](https://github.com/python-kasa/python-kasa/pull/956) (@rytilahti)
- Do not raise on multi-request errors on child devices [\#949](https://github.com/python-kasa/python-kasa/pull/949) (@rytilahti)
- Fix P100 errors on multi-requests [\#930](https://github.com/python-kasa/python-kasa/pull/930) (@sdb9696)
- Retry query on 403 after successful handshake [\#785](https://github.com/python-kasa/python-kasa/pull/785) (@sdb9696)
- Ensure connections are closed when cli is finished [\#752](https://github.com/python-kasa/python-kasa/pull/752) (@sdb9696)
- Fix for P100 on fw 1.1.3 login\_version none [\#751](https://github.com/python-kasa/python-kasa/pull/751) (@sdb9696)
- Pass timeout parameters to discover\_single [\#744](https://github.com/python-kasa/python-kasa/pull/744) (@sdb9696)
- Reduce AuthenticationExceptions raising from transports [\#740](https://github.com/python-kasa/python-kasa/pull/740) (@sdb9696)
- Do not crash cli on missing discovery info [\#735](https://github.com/python-kasa/python-kasa/pull/735) (@rytilahti)
- Fix port-override for aes&klap transports [\#734](https://github.com/python-kasa/python-kasa/pull/734) (@rytilahti)
- Fix discovery cli to print devices not printed during discovery timeout [\#670](https://github.com/python-kasa/python-kasa/pull/670) (@sdb9696)

**Added support for devices:**

- Add fixture for L920-5\(EU\) 1.0.7 [\#972](https://github.com/python-kasa/python-kasa/pull/972) (@rytilahti)
- Add P115 fixture [\#950](https://github.com/python-kasa/python-kasa/pull/950) (@rytilahti)
- Add some device fixtures [\#948](https://github.com/python-kasa/python-kasa/pull/948) (@rytilahti)
- Add fixture for S505D [\#947](https://github.com/python-kasa/python-kasa/pull/947) (@rytilahti)
- Add fixture for p300 1.0.15 [\#915](https://github.com/python-kasa/python-kasa/pull/915) (@rytilahti)
- Add H100 1.5.10 and KE100 2.4.0 fixtures [\#905](https://github.com/python-kasa/python-kasa/pull/905) (@rytilahti)
- Add fixture for waterleak sensor T300 [\#897](https://github.com/python-kasa/python-kasa/pull/897) (@rytilahti)
- Add support for contact sensor \(T110\) [\#877](https://github.com/python-kasa/python-kasa/pull/877) (@rytilahti)
- Add support for waterleak sensor \(T300\) [\#876](https://github.com/python-kasa/python-kasa/pull/876) (@rytilahti)
- Add support for KH100 hub [\#847](https://github.com/python-kasa/python-kasa/pull/847) (@Adriandorr)
- Support for new ks240 fan/light wall switch [\#839](https://github.com/python-kasa/python-kasa/pull/839) (@sdb9696)
- Add P100 fw 1.4.0 fixture [\#820](https://github.com/python-kasa/python-kasa/pull/820) (@sdb9696)
- Add fixture for P110 sw 1.0.7 [\#801](https://github.com/python-kasa/python-kasa/pull/801) (@rytilahti)
- Add updated l530 fixture 1.1.6 [\#792](https://github.com/python-kasa/python-kasa/pull/792) (@rytilahti)
- Fix devtools for P100 and add fixture [\#753](https://github.com/python-kasa/python-kasa/pull/753) (@sdb9696)
- Add H100 fixtures [\#737](https://github.com/python-kasa/python-kasa/pull/737) (@rytilahti)

**Documentation updates:**

- Document device features [\#755](https://github.com/python-kasa/python-kasa/issues/755)
- Clean up the README [\#979](https://github.com/python-kasa/python-kasa/issues/979)
- Cleanup README to use the new cli format [\#999](https://github.com/python-kasa/python-kasa/pull/999) (@rytilahti)
- Add 0.7 api changes section to docs [\#996](https://github.com/python-kasa/python-kasa/pull/996) (@sdb9696)
- Update docs with more howto examples [\#968](https://github.com/python-kasa/python-kasa/pull/968) (@sdb9696)
- Update documentation structure and start migrating to markdown [\#934](https://github.com/python-kasa/python-kasa/pull/934) (@sdb9696)
- Add tutorial doctest module and enable top level await [\#919](https://github.com/python-kasa/python-kasa/pull/919) (@sdb9696)
- Add warning about tapo watchdog [\#902](https://github.com/python-kasa/python-kasa/pull/902) (@rytilahti)
- Move contribution instructions into docs [\#901](https://github.com/python-kasa/python-kasa/pull/901) (@rytilahti)
- Add rust tapo link to README [\#857](https://github.com/python-kasa/python-kasa/pull/857) (@rytilahti)
- Update README to be more approachable for new users [\#994](https://github.com/python-kasa/python-kasa/pull/994) (@rytilahti)
- Enable shell extra for installing ptpython and rich [\#782](https://github.com/python-kasa/python-kasa/pull/782) (@sdb9696)
- Add WallSwitch device type and autogenerate supported devices docs [\#758](https://github.com/python-kasa/python-kasa/pull/758) (@sdb9696)

**Project maintenance:**

- Remove anyio dependency from pyproject.toml [\#990](https://github.com/python-kasa/python-kasa/pull/990) (@sdb9696)
- Configure mypy to run in virtual environment and fix resulting issues [\#989](https://github.com/python-kasa/python-kasa/pull/989) (@sdb9696)
- Better checking of child modules not supported by parent device [\#966](https://github.com/python-kasa/python-kasa/pull/966) (@sdb9696)
- Use freezegun for testing aes http client delays [\#954](https://github.com/python-kasa/python-kasa/pull/954) (@sdb9696)
- Fix passing custom port for dump\_devinfo [\#938](https://github.com/python-kasa/python-kasa/pull/938) (@rytilahti)
- Update release playbook [\#932](https://github.com/python-kasa/python-kasa/pull/932) (@rytilahti)
- Deprecate device level light, effect and led attributes [\#916](https://github.com/python-kasa/python-kasa/pull/916) (@sdb9696)
- Update cli to use common modules and remove iot specific cli testing [\#913](https://github.com/python-kasa/python-kasa/pull/913) (@sdb9696)
- Deprecate is\_something attributes [\#912](https://github.com/python-kasa/python-kasa/pull/912) (@sdb9696)
- Rename bulb interface to light and move fan and light interface to interfaces [\#910](https://github.com/python-kasa/python-kasa/pull/910) (@sdb9696)
- Make module names consistent and remove redundant module casting [\#909](https://github.com/python-kasa/python-kasa/pull/909) (@sdb9696)
- Add child devices from hubs to generated list of supported devices [\#898](https://github.com/python-kasa/python-kasa/pull/898) (@sdb9696)
- Update interfaces so they all inherit from Device [\#893](https://github.com/python-kasa/python-kasa/pull/893) (@sdb9696)
- Update ks240 fixture with child device query info [\#890](https://github.com/python-kasa/python-kasa/pull/890) (@sdb9696)
- Use pydantic.v1 namespace on all pydantic versions [\#883](https://github.com/python-kasa/python-kasa/pull/883) (@rytilahti)
- Update dump\_devinfo to print original exception stack on errors. [\#882](https://github.com/python-kasa/python-kasa/pull/882) (@sdb9696)
- Put modules back on children for wall switches [\#881](https://github.com/python-kasa/python-kasa/pull/881) (@sdb9696)
- Fix pypy39 CI cache on macos [\#868](https://github.com/python-kasa/python-kasa/pull/868) (@sdb9696)
- Do not try coverage upload for pypy [\#867](https://github.com/python-kasa/python-kasa/pull/867) (@sdb9696)
- Add runner.arch to cache-key in CI [\#866](https://github.com/python-kasa/python-kasa/pull/866) (@sdb9696)
- Fix broken CI due to missing python version on macos-latest [\#864](https://github.com/python-kasa/python-kasa/pull/864) (@sdb9696)
- Fix incorrect state updates in FakeTestProtocols [\#861](https://github.com/python-kasa/python-kasa/pull/861) (@sdb9696)
- Embed FeatureType inside Feature [\#860](https://github.com/python-kasa/python-kasa/pull/860) (@rytilahti)
- Include component\_nego with child fixtures [\#858](https://github.com/python-kasa/python-kasa/pull/858) (@sdb9696)
- Use brightness module for smartbulb [\#853](https://github.com/python-kasa/python-kasa/pull/853) (@rytilahti)
- Ignore system environment variables for tests [\#851](https://github.com/python-kasa/python-kasa/pull/851) (@rytilahti)
- Remove mock fixtures [\#845](https://github.com/python-kasa/python-kasa/pull/845) (@rytilahti)
- Enable and convert to future annotations [\#838](https://github.com/python-kasa/python-kasa/pull/838) (@sdb9696)
- Update poetry locks and pre-commit hooks [\#837](https://github.com/python-kasa/python-kasa/pull/837) (@sdb9696)
- Cache pipx in CI and add custom setup action [\#835](https://github.com/python-kasa/python-kasa/pull/835) (@sdb9696)
- Fix non python 3.8 compliant test [\#832](https://github.com/python-kasa/python-kasa/pull/832) (@sdb9696)
- Fix CI issue with python version used by pipx to install poetry [\#831](https://github.com/python-kasa/python-kasa/pull/831) (@sdb9696)
- Refactor split smartdevice tests to test\_{iot,smart}device [\#822](https://github.com/python-kasa/python-kasa/pull/822) (@rytilahti)
- Add pre-commit caching and fix poetry extras cache [\#817](https://github.com/python-kasa/python-kasa/pull/817) (@sdb9696)
- Fix slow aestransport and cli tests [\#816](https://github.com/python-kasa/python-kasa/pull/816) (@sdb9696)
- Do not run coverage on pypy and cache poetry envs [\#812](https://github.com/python-kasa/python-kasa/pull/812) (@sdb9696)
- Update test framework for dynamic parametrization [\#810](https://github.com/python-kasa/python-kasa/pull/810) (@sdb9696)
- Put child fixtures in subfolder [\#809](https://github.com/python-kasa/python-kasa/pull/809) (@sdb9696)
- Simplify device \_\_repr\_\_ [\#805](https://github.com/python-kasa/python-kasa/pull/805) (@rytilahti)
- Add T315 fixture, tests for humidity&temperature modules [\#802](https://github.com/python-kasa/python-kasa/pull/802) (@rytilahti)
- Do not fail fast on pypy CI jobs [\#799](https://github.com/python-kasa/python-kasa/pull/799) (@sdb9696)
- Update dump\_devinfo to collect child device info [\#796](https://github.com/python-kasa/python-kasa/pull/796) (@sdb9696)
- Refactor test framework [\#794](https://github.com/python-kasa/python-kasa/pull/794) (@sdb9696)
- Refactor devices into subpackages and deprecate old names [\#716](https://github.com/python-kasa/python-kasa/pull/716) (@sdb9696)
- Drop python3.8 support [\#992](https://github.com/python-kasa/python-kasa/pull/992) (@rytilahti)
- Make Light and Fan a common module interface [\#911](https://github.com/python-kasa/python-kasa/pull/911) (@sdb9696)
- Add missing firmware module import [\#774](https://github.com/python-kasa/python-kasa/pull/774) (@rytilahti)
- Fix dump\_devinfo scrubbing for ks240 [\#765](https://github.com/python-kasa/python-kasa/pull/765) (@rytilahti)
- Rename and deprecate exception classes [\#739](https://github.com/python-kasa/python-kasa/pull/739) (@sdb9696)

**Closed issues:**

- Improve timezone support [\#980](https://github.com/python-kasa/python-kasa/issues/980)

## [0.6.2.1](https://github.com/python-kasa/python-kasa/tree/0.6.2.1) (2024-02-02)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.6.2...0.6.2.1)

**Fixed bugs:**

- Avoid crashing on childdevice property accesses [\#732](https://github.com/python-kasa/python-kasa/pull/732) (@rytilahti)

**Added support for devices:**

- Add TP15 fixture [\#730](https://github.com/python-kasa/python-kasa/pull/730) (@bdraco)
- Add TP25 fixtures [\#729](https://github.com/python-kasa/python-kasa/pull/729) (@bdraco)

**Project maintenance:**

- Various test code cleanups [\#725](https://github.com/python-kasa/python-kasa/pull/725) (@rytilahti)
- Unignore F401 for tests [\#724](https://github.com/python-kasa/python-kasa/pull/724) (@rytilahti)

**Merged pull requests:**

- Retain last two chars for children device\_id [\#733](https://github.com/python-kasa/python-kasa/pull/733) (@rytilahti)

## [0.6.2](https://github.com/python-kasa/python-kasa/tree/0.6.2) (2024-01-29)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.6.1...0.6.2)

Release highlights:
* Support for tapo power strips (P300)
* Performance improvements and bug fixes

**Implemented enhancements:**

- Implement alias set for tapodevice [\#721](https://github.com/python-kasa/python-kasa/pull/721) (@rytilahti)
- Reduce the number of times creating the cipher in klap [\#712](https://github.com/python-kasa/python-kasa/pull/712) (@bdraco)
- Use hashlib for klap [\#711](https://github.com/python-kasa/python-kasa/pull/711) (@bdraco)
- Initial support for tapos with child devices [\#720](https://github.com/python-kasa/python-kasa/pull/720) (@rytilahti)
- Avoid rebuilding urls for every request [\#715](https://github.com/python-kasa/python-kasa/pull/715) (@bdraco)
- Enable batching of multiple requests [\#662](https://github.com/python-kasa/python-kasa/pull/662) (@sdb9696)
- Sleep between discovery packets [\#656](https://github.com/python-kasa/python-kasa/pull/656) (@sdb9696)

**Fixed bugs:**

- Fix TapoBulb state information for non-dimmable SMARTSWITCH [\#726](https://github.com/python-kasa/python-kasa/pull/726) (@sdb9696)

**Added support for devices:**

- Update L510E\(US\) fixture with mac prefix [\#722](https://github.com/python-kasa/python-kasa/pull/722) (@sdb9696)
- Add P300 fixture [\#717](https://github.com/python-kasa/python-kasa/pull/717) (@rytilahti)

**Documentation updates:**

- Add protocol and transport documentation [\#663](https://github.com/python-kasa/python-kasa/pull/663) (@sdb9696)

**Project maintenance:**

- Use hashlib in place of hashes.Hash [\#714](https://github.com/python-kasa/python-kasa/pull/714) (@bdraco)
- Switch from TPLinkSmartHomeProtocol to IotProtocol/XorTransport [\#710](https://github.com/python-kasa/python-kasa/pull/710) (@sdb9696)

**Merged pull requests:**

- Add concrete XorTransport class with full implementation [\#646](https://github.com/python-kasa/python-kasa/pull/646) (@sdb9696)

## [0.6.1](https://github.com/python-kasa/python-kasa/tree/0.6.1) (2024-01-25)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.6.0.1...0.6.1)

Release highlights:
* Support for tapo wall switches
* Support for unprovisioned devices
* Performance and stability improvements

**Implemented enhancements:**

- Add support for tapo wall switches \(S500D\) [\#704](https://github.com/python-kasa/python-kasa/pull/704) (@bdraco)
- Add L930-5 fixture [\#694](https://github.com/python-kasa/python-kasa/pull/694) (@bdraco)
- Add fixtures for L510E [\#693](https://github.com/python-kasa/python-kasa/pull/693) (@bdraco)
- Add new cli command 'command' to execute arbitrary commands [\#692](https://github.com/python-kasa/python-kasa/pull/692) (@rytilahti)
- Allow raw-command and wifi without update [\#688](https://github.com/python-kasa/python-kasa/pull/688) (@rytilahti)
- Generate AES KeyPair lazily [\#687](https://github.com/python-kasa/python-kasa/pull/687) (@sdb9696)
- Add reboot and factory\_reset to tapodevice [\#686](https://github.com/python-kasa/python-kasa/pull/686) (@rytilahti)
- Try default tapo credentials for klap and aes [\#685](https://github.com/python-kasa/python-kasa/pull/685) (@sdb9696)

**Fixed bugs:**

- Do not crash on missing geolocation [\#701](https://github.com/python-kasa/python-kasa/pull/701) (@rytilahti)
- Fix P100 error getting conn closed when trying default login after login failure [\#690](https://github.com/python-kasa/python-kasa/pull/690) (@sdb9696)

**Documentation updates:**

- Document authenticated provisioning [\#634](https://github.com/python-kasa/python-kasa/pull/634) (@rytilahti)

**Project maintenance:**

- Add additional L900-10 fixture [\#707](https://github.com/python-kasa/python-kasa/pull/707) (@bdraco)
- Replace rich formatting stripper [\#706](https://github.com/python-kasa/python-kasa/pull/706) (@bdraco)

**Merged pull requests:**

- Fix overly greedy \_strip\_rich\_formatting [\#703](https://github.com/python-kasa/python-kasa/pull/703) (@bdraco)
- Update readme fixture checker and readme [\#699](https://github.com/python-kasa/python-kasa/pull/699) (@rytilahti)
- Update transport close/reset behaviour [\#689](https://github.com/python-kasa/python-kasa/pull/689) (@sdb9696)
- Check README for supported models [\#684](https://github.com/python-kasa/python-kasa/pull/684) (@rytilahti)
- Add P100 test fixture [\#683](https://github.com/python-kasa/python-kasa/pull/683) (@bdraco)
- Make dump\_devinfo request batch size configurable [\#681](https://github.com/python-kasa/python-kasa/pull/681) (@sdb9696)
- Add updated L920 fixture [\#680](https://github.com/python-kasa/python-kasa/pull/680) (@bdraco)
- Update fixtures from test devices [\#679](https://github.com/python-kasa/python-kasa/pull/679) (@bdraco)
- Show discovery data for state with verbose [\#678](https://github.com/python-kasa/python-kasa/pull/678) (@rytilahti)
- Add L530E\(US\) fixture [\#674](https://github.com/python-kasa/python-kasa/pull/674) (@bdraco)
- Add P135 fixture [\#673](https://github.com/python-kasa/python-kasa/pull/673) (@bdraco)
- Rename base TPLinkProtocol to BaseProtocol [\#669](https://github.com/python-kasa/python-kasa/pull/669) (@sdb9696)
- Add support for the S500 [\#705](https://github.com/python-kasa/python-kasa/pull/705) (@bdraco)
- Ensure login token is only sent if aes state is ESTABLISHED [\#702](https://github.com/python-kasa/python-kasa/pull/702) (@bdraco)
- Fix test\_klapprotocol test duration [\#698](https://github.com/python-kasa/python-kasa/pull/698) (@sdb9696)
- Renew the handshake session 20 minutes before we think it will expire [\#697](https://github.com/python-kasa/python-kasa/pull/697) (@bdraco)
- Add --batch-size hint to timeout errors in dump\_devinfo [\#696](https://github.com/python-kasa/python-kasa/pull/696) (@sdb9696)
- Refactor aestransport to use a state enum [\#691](https://github.com/python-kasa/python-kasa/pull/691) (@bdraco)
- Add 1003 \(TRANSPORT\_UNKNOWN\_CREDENTIALS\_ERROR\) [\#667](https://github.com/python-kasa/python-kasa/pull/667) (@rytilahti)

## [0.6.0.1](https://github.com/python-kasa/python-kasa/tree/0.6.0.1) (2024-01-21)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.6.0...0.6.0.1)

A patch release to improve the protocol handling.

**Fixed bugs:**

- Fix httpclient exceptions on read and improve error info [\#655](https://github.com/python-kasa/python-kasa/pull/655) (@sdb9696)
- Improve and document close behavior  [\#654](https://github.com/python-kasa/python-kasa/pull/654) (@bdraco)

**Merged pull requests:**

- Add l900-5 1.1.0 fixture [\#664](https://github.com/python-kasa/python-kasa/pull/664) (@rytilahti)
- Add fixtures with new MAC mask [\#661](https://github.com/python-kasa/python-kasa/pull/661) (@sdb9696)
- Make close behaviour consistent across new protocols and transports [\#660](https://github.com/python-kasa/python-kasa/pull/660) (@sdb9696)
- Fix minor typos in docstrings [\#659](https://github.com/python-kasa/python-kasa/pull/659) (@bdraco)
- dump\_devinfo improvements [\#657](https://github.com/python-kasa/python-kasa/pull/657) (@rytilahti)

## [0.6.0](https://github.com/python-kasa/python-kasa/tree/0.6.0) (2024-01-19)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.5.4...0.6.0)

This major brings major changes to the library by adding support for devices that require authentication for communications, all of this being possible thanks to the great work by @sdb9696!

This release adds support to a large range of previously unsupported devices, including:

* Newer kasa-branded devices, including Matter-enabled devices like KP125M
* Newer hardware/firmware versions on some models, like EP25, that suddenly changed the used protocol
* Tapo-branded devices like plugs (P110), light bulbs (KL530), LED strips (L900, L920), and wall switches (KS205, KS225)
* UK variant of HS110, which was the first device using the new protocol

If your device that is not currently listed as supported is working, please consider contributing a test fixture file.

Special thanks goes to @SimonWilkinson who created the initial PR for the new communication protocol!

**Breaking changes:**

- Add DeviceConfig to allow specifying configuration parameters [\#569](https://github.com/python-kasa/python-kasa/pull/569) (@sdb9696)
- Move connect\_single to SmartDevice.connect [\#538](https://github.com/python-kasa/python-kasa/pull/538) (@bdraco)

**Implemented enhancements:**

- Support for KS225\(US\) Light Dimmer and KS205\(US\) Light Switch [\#589](https://github.com/python-kasa/python-kasa/issues/589)
- Set timeout using command line parameters [\#310](https://github.com/python-kasa/python-kasa/issues/310)
- Implement the new protocol \(HTTP over 80/tcp, 20002/udp for discovery\) [\#115](https://github.com/python-kasa/python-kasa/issues/115)
- Get child emeters with CLI [\#623](https://github.com/python-kasa/python-kasa/pull/623) (@Obbay2)
- Avoid linear search for emeter realtime and emeter\_today [\#622](https://github.com/python-kasa/python-kasa/pull/622) (@bdraco)
- Add update-credentials command [\#620](https://github.com/python-kasa/python-kasa/pull/620) (@rytilahti)
- Enable multiple requests in smartprotocol [\#584](https://github.com/python-kasa/python-kasa/pull/584) (@sdb9696)
- Improve CLI Discovery output [\#583](https://github.com/python-kasa/python-kasa/pull/583) (@sdb9696)
- Improve smartprotocol error handling and retries [\#578](https://github.com/python-kasa/python-kasa/pull/578) (@sdb9696)
- Request component\_nego only once for tapodevice [\#576](https://github.com/python-kasa/python-kasa/pull/576) (@rytilahti)
- Use consistent naming for cli envvars [\#570](https://github.com/python-kasa/python-kasa/pull/570) (@rytilahti)
- Add KP125M fixture and allow passing credentials for tests [\#567](https://github.com/python-kasa/python-kasa/pull/567) (@sbytnar)
- Make timeout configurable for cli [\#564](https://github.com/python-kasa/python-kasa/pull/564) (@rytilahti)
- Update dump\_devinfo to produce new TAPO/SMART fixtures [\#561](https://github.com/python-kasa/python-kasa/pull/561) (@sdb9696)
- Kasa KP125M basic emeter support [\#560](https://github.com/python-kasa/python-kasa/pull/560) (@sbytnar)
- Add klap support for TAPO protocol by splitting out Transports and Protocols [\#557](https://github.com/python-kasa/python-kasa/pull/557) (@sdb9696)
- Update dump\_devinfo to include 20002 discovery results [\#556](https://github.com/python-kasa/python-kasa/pull/556) (@sdb9696)
- Set TCP\_NODELAY to avoid needless buffering [\#554](https://github.com/python-kasa/python-kasa/pull/554) (@bdraco)
- Add support for the protocol used by TAPO devices and some newer KASA devices. [\#552](https://github.com/python-kasa/python-kasa/pull/552) (@sdb9696)
- Re-add protocol\_class parameter to connect [\#551](https://github.com/python-kasa/python-kasa/pull/551) (@sdb9696)
- Update discover single to handle hostnames [\#539](https://github.com/python-kasa/python-kasa/pull/539) (@sdb9696)
- Allow serializing and passing of credentials\_hashes in DeviceConfig [\#607](https://github.com/python-kasa/python-kasa/pull/607) (@sdb9696)
- Implement wifi interface for tapodevice [\#606](https://github.com/python-kasa/python-kasa/pull/606) (@rytilahti)
- Add support for KS205 and KS225 wall switches [\#594](https://github.com/python-kasa/python-kasa/pull/594) (@gimpy88)
- Add support for tapo bulbs [\#558](https://github.com/python-kasa/python-kasa/pull/558) (@rytilahti)
- Add klap protocol [\#509](https://github.com/python-kasa/python-kasa/pull/509) (@sdb9696)

**Fixed bugs:**

- dump\_devinfo crashes when credentials are not given [\#591](https://github.com/python-kasa/python-kasa/issues/591)
- Fix connection indeterminate state on cancellation [\#636](https://github.com/python-kasa/python-kasa/pull/636) (@bdraco)
- Check the ct range for color temp support [\#619](https://github.com/python-kasa/python-kasa/pull/619) (@rytilahti)
- Fix cli discover bug with None username/password [\#615](https://github.com/python-kasa/python-kasa/pull/615) (@sdb9696)
- Fix hsv setting for tapobulb [\#573](https://github.com/python-kasa/python-kasa/pull/573) (@rytilahti)
- Fix transport retries after close [\#568](https://github.com/python-kasa/python-kasa/pull/568) (@sdb9696)

**Documentation updates:**

- Update the documentation for 0.6 release [\#600](https://github.com/python-kasa/python-kasa/issues/600)
- Update docs for newer devices and DeviceConfig [\#614](https://github.com/python-kasa/python-kasa/pull/614) (@sdb9696)
- Update readme with clearer instructions, tapo support [\#571](https://github.com/python-kasa/python-kasa/pull/571) (@rytilahti)
- Add some more external links to README [\#541](https://github.com/python-kasa/python-kasa/pull/541) (@rytilahti)

**Merged pull requests:**

- Remove time logging in debug message [\#645](https://github.com/python-kasa/python-kasa/pull/645) (@sdb9696)
- Migrate http client to use aiohttp instead of httpx [\#643](https://github.com/python-kasa/python-kasa/pull/643) (@sdb9696)
- Encapsulate http client dependency [\#642](https://github.com/python-kasa/python-kasa/pull/642) (@sdb9696)
- Fix broken docs due to applehelp dependency [\#641](https://github.com/python-kasa/python-kasa/pull/641) (@sdb9696)
- Raise SmartDeviceException on invalid config dicts [\#640](https://github.com/python-kasa/python-kasa/pull/640) (@sdb9696)
- Add fixture for L920 [\#638](https://github.com/python-kasa/python-kasa/pull/638) (@bdraco)
- Raise TimeoutException on discover\_single timeout [\#632](https://github.com/python-kasa/python-kasa/pull/632) (@sdb9696)
- Add L900-10 fixture and it's additional component requests [\#629](https://github.com/python-kasa/python-kasa/pull/629) (@sdb9696)
- Avoid recreating struct each request in legacy protocol [\#628](https://github.com/python-kasa/python-kasa/pull/628) (@bdraco)
- Return alias as None for new discovery devices before update [\#627](https://github.com/python-kasa/python-kasa/pull/627) (@sdb9696)
- Update config to\_dict to exclude credentials if the hash is empty string [\#626](https://github.com/python-kasa/python-kasa/pull/626) (@sdb9696)
- Improve test coverage [\#625](https://github.com/python-kasa/python-kasa/pull/625) (@sdb9696)
- Add P125M and update EP25 fixtures [\#621](https://github.com/python-kasa/python-kasa/pull/621) (@bdraco)
- Use consistent envvars for dump\_devinfo credentials [\#618](https://github.com/python-kasa/python-kasa/pull/618) (@rytilahti)
- Mark L900-5 as supported [\#617](https://github.com/python-kasa/python-kasa/pull/617) (@rytilahti)
- Ship CHANGELOG only in sdist [\#610](https://github.com/python-kasa/python-kasa/pull/610) (@rytilahti)
- Cleanup credentials handling [\#605](https://github.com/python-kasa/python-kasa/pull/605) (@rytilahti)
- Update P110\(EU\) fixture [\#604](https://github.com/python-kasa/python-kasa/pull/604) (@rytilahti)
- Update L530 aes fixture [\#603](https://github.com/python-kasa/python-kasa/pull/603) (@rytilahti)
- Cleanup custom exception kwarg handling [\#602](https://github.com/python-kasa/python-kasa/pull/602) (@rytilahti)
- Pull up emeter handling to tapodevice base class [\#601](https://github.com/python-kasa/python-kasa/pull/601) (@rytilahti)
- Add L530\(EU\) klap fixture [\#598](https://github.com/python-kasa/python-kasa/pull/598) (@sdb9696)
- Update P110\(UK\) fixture [\#596](https://github.com/python-kasa/python-kasa/pull/596) (@sdb9696)
- Fix dump\_devinfo for unauthenticated [\#593](https://github.com/python-kasa/python-kasa/pull/593) (@sdb9696)
- Elevate --verbose to top-level option [\#590](https://github.com/python-kasa/python-kasa/pull/590) (@rytilahti)
- Add optional error code to exceptions [\#585](https://github.com/python-kasa/python-kasa/pull/585) (@sdb9696)
- Fix typo in cli.rst [\#581](https://github.com/python-kasa/python-kasa/pull/581) (@alanblake)
- Do login entirely within AesTransport [\#580](https://github.com/python-kasa/python-kasa/pull/580) (@sdb9696)
- Log smartprotocol requests [\#575](https://github.com/python-kasa/python-kasa/pull/575) (@rytilahti)
- Add new methods to dump\_devinfo and mask aliases [\#574](https://github.com/python-kasa/python-kasa/pull/574) (@sdb9696)
- Add EP25 smart fixture and improve test framework for SMART devices [\#572](https://github.com/python-kasa/python-kasa/pull/572) (@sdb9696)
- Re-add regional suffix to TAPO/SMART fixtures [\#566](https://github.com/python-kasa/python-kasa/pull/566) (@sdb9696)
- Add P110 fixture [\#562](https://github.com/python-kasa/python-kasa/pull/562) (@rytilahti)
- Do not do update\(\) in discover\_single [\#542](https://github.com/python-kasa/python-kasa/pull/542) (@sdb9696)
- Add known smart requests to dump\_devinfo [\#597](https://github.com/python-kasa/python-kasa/pull/597) (@sdb9696)

## [0.5.4](https://github.com/python-kasa/python-kasa/tree/0.5.4) (2023-10-29)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.5.3...0.5.4)

The highlights of this maintenance release:

* Support to the alternative discovery protocol and foundational work to support other communication protocols, thanks to @sdb9696.
* Reliability improvements by avoiding overflowing device buffers, thanks to @cobryan05.
* Optimizations for downstream device accesses, thanks to @bdraco.
* Support for both pydantic v1 and v2.

As always, see the full changelog for details.

**Implemented enhancements:**

- Add a connect\_single method to Discover to avoid the need for UDP [\#528](https://github.com/python-kasa/python-kasa/pull/528) (@bdraco)
- Parse features only during updates [\#527](https://github.com/python-kasa/python-kasa/pull/527) (@bdraco)
- Show an error if both --alias and --host are defined [\#513](https://github.com/python-kasa/python-kasa/pull/513) (@rytilahti)
- Add plumbing for passing credentials to devices [\#507](https://github.com/python-kasa/python-kasa/pull/507) (@sdb9696)
- Add support for pydantic v2 using v1 shims [\#504](https://github.com/python-kasa/python-kasa/pull/504) (@rytilahti)
- Split queries to avoid overflowing device buffers [\#502](https://github.com/python-kasa/python-kasa/pull/502) (@cobryan05)
- Add toggle command to cli [\#498](https://github.com/python-kasa/python-kasa/pull/498) (@normanr)
- Add support for alternative discovery protocol \(20002/udp\) [\#488](https://github.com/python-kasa/python-kasa/pull/488) (@sdb9696)
- Add discovery timeout parameter [\#486](https://github.com/python-kasa/python-kasa/pull/486) (@sdb9696)
- Add devtools script to create module fixtures [\#404](https://github.com/python-kasa/python-kasa/pull/404) (@rytilahti)
- Make timeout adjustable [\#494](https://github.com/python-kasa/python-kasa/pull/494) (@bdraco)

**Fixed bugs:**

- Fix on\_since for smartstrip sockets [\#529](https://github.com/python-kasa/python-kasa/pull/529) (@rytilahti)
- Fix every other query tries to fetch known unsupported features [\#520](https://github.com/python-kasa/python-kasa/pull/520) (@bdraco)

**Documentation updates:**

- Mark KS2{20}M as partially supported [\#508](https://github.com/python-kasa/python-kasa/pull/508) (@lschweiss)
- Document cli tool --target for discovery [\#497](https://github.com/python-kasa/python-kasa/pull/497) (@rytilahti)

**Merged pull requests:**

- Use ruff and ruff format [\#534](https://github.com/python-kasa/python-kasa/pull/534) (@rytilahti)
- Add python3.12 and pypy-3.10 to CI [\#532](https://github.com/python-kasa/python-kasa/pull/532) (@rytilahti)
- Use trusted publisher for publishing to pypi [\#531](https://github.com/python-kasa/python-kasa/pull/531) (@rytilahti)
- Remove code to detect event loop change [\#526](https://github.com/python-kasa/python-kasa/pull/526) (@bdraco)
- Convert readthedocs config to v2 [\#505](https://github.com/python-kasa/python-kasa/pull/505) (@rytilahti)
- Add new HS100\(UK\) fixture [\#489](https://github.com/python-kasa/python-kasa/pull/489) (@sdb9696)
- Update pyproject.toml isort profile, dev group header and poetry.lock [\#487](https://github.com/python-kasa/python-kasa/pull/487) (@sdb9696)

## [0.5.3](https://github.com/python-kasa/python-kasa/tree/0.5.3) (2023-07-23)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.5.2...0.5.3)

This release adds support for defining the device port and introduces dependency on async-timeout which improves timeout handling.

**Implemented enhancements:**

- Make device port configurable [\#471](https://github.com/python-kasa/python-kasa/pull/471) (@karpach)

**Fixed bugs:**

- Replace asyncio.wait\_for with async-timeout [\#480](https://github.com/python-kasa/python-kasa/pull/480) (@bdraco)

**Merged pull requests:**

- Add tests for KP200 [\#483](https://github.com/python-kasa/python-kasa/pull/483) (@bdraco)
- Update pyyaml to fix CI [\#482](https://github.com/python-kasa/python-kasa/pull/482) (@bdraco)

## [0.5.2](https://github.com/python-kasa/python-kasa/tree/0.5.2) (2023-07-02)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.5.1...0.5.2)

Besides some small improvements, this release:
* Adds optional dependency for for `orjson` and `kasa-crypt` to speed-up protocol handling by an order of magnitude.
* Drops Python 3.7 support as it is no longer maintained.

**Breaking changes:**

- Drop python 3.7 support [\#455](https://github.com/python-kasa/python-kasa/pull/455) (@rytilahti)

**Implemented enhancements:**

- Use orjson when already installed or with speedups extra [\#466](https://github.com/python-kasa/python-kasa/pull/466) (@bdraco)
- Add optional kasa-crypt dependency for speedups [\#464](https://github.com/python-kasa/python-kasa/pull/464) (@bdraco)
- Add inactivity setting for the motion module [\#453](https://github.com/python-kasa/python-kasa/pull/453) (@rytilahti)
- Add methods to configure dimmer settings [\#429](https://github.com/python-kasa/python-kasa/pull/429) (@rytilahti)

**Fixed bugs:**

- Request for KP405 Support - Dimmable Plug [\#469](https://github.com/python-kasa/python-kasa/issues/469)
- Issue printing device in on\_discovered: pydantic.error\_wrappers.ValidationError: 3 validation errors for SmartBulbPreset [\#439](https://github.com/python-kasa/python-kasa/issues/439)
- Possible firmware issue with KL125 \(1.0.7 Build 211009 Rel.172044\) [\#345](https://github.com/python-kasa/python-kasa/issues/345)
- Exclude querying certain modules for KL125\(US\) which cause crashes  [\#451](https://github.com/python-kasa/python-kasa/pull/451) (@brianthedavis)
- Return result objects for cli discover and implicit 'state' [\#446](https://github.com/python-kasa/python-kasa/pull/446) (@rytilahti)
- Allow effect presets seen on light strips [\#440](https://github.com/python-kasa/python-kasa/pull/440) (@rytilahti)

**Merged pull requests:**

- Add benchmarks for speedups [\#473](https://github.com/python-kasa/python-kasa/pull/473) (@bdraco)
- Add fixture for KP405 Smart Dimmer Plug [\#470](https://github.com/python-kasa/python-kasa/pull/470) (@xinud190)
- Remove importlib-metadata dependency [\#457](https://github.com/python-kasa/python-kasa/pull/457) (@rytilahti)
- Update dependencies to fix CI [\#454](https://github.com/python-kasa/python-kasa/pull/454) (@rytilahti)
- Cleanup fixture filenames [\#448](https://github.com/python-kasa/python-kasa/pull/448) (@rytilahti)

## [0.5.1](https://github.com/python-kasa/python-kasa/tree/0.5.1) (2023-02-18)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.5.0...0.5.1)

This minor release contains mostly small UX fine-tuning and documentation improvements alongside with bug fixes:
* Improved console tool (JSON output, colorized output if rich is installed)
* Pretty, colorized console output, if `rich` is installed
* Support for configuring bulb presets
* Usage data is now reported in the expected format
* Dependency pinning is relaxed to give downstreams more control

**Breaking changes:**

- Implement changing the bulb turn-on behavior [\#381](https://github.com/python-kasa/python-kasa/pull/381) (@rytilahti)

**Implemented enhancements:**

- Pretty-print all exceptions from cli commands [\#428](https://github.com/python-kasa/python-kasa/pull/428) (@rytilahti)
- Add transition parameter to lightstrip's set\_effect [\#416](https://github.com/python-kasa/python-kasa/pull/416) (@rytilahti)
- Add brightness to lightstrip's set\_effect [\#415](https://github.com/python-kasa/python-kasa/pull/415) (@rytilahti)
- Use rich for prettier output, if available [\#403](https://github.com/python-kasa/python-kasa/pull/403) (@rytilahti)
- Adding cli command to delete a schedule rule [\#391](https://github.com/python-kasa/python-kasa/pull/391) (@aricforrest)
- Add support for bulb presets [\#379](https://github.com/python-kasa/python-kasa/pull/379) (@rytilahti)
- Add support for json output [\#430](https://github.com/python-kasa/python-kasa/pull/430) (@rytilahti)

**Fixed bugs:**

- cli.py usage year and month options do not output data as expected [\#373](https://github.com/python-kasa/python-kasa/issues/373)
- cli.py usage --year command passes year argument incorrectly [\#371](https://github.com/python-kasa/python-kasa/issues/371)
- KP303 reporting as device off [\#319](https://github.com/python-kasa/python-kasa/issues/319)
- HS210 not updating the state correctly [\#193](https://github.com/python-kasa/python-kasa/issues/193)
- Fix year emeter for cli by using kwarg for year parameter [\#372](https://github.com/python-kasa/python-kasa/pull/372) (@rytilahti)
- Return usage.get\_{monthstat,daystat} in expected format  [\#394](https://github.com/python-kasa/python-kasa/pull/394) (@jules43)

**Documentation updates:**

- Update misleading docs about supported devices \(was: add support for EP25 plug\) [\#367](https://github.com/python-kasa/python-kasa/issues/367)
- Minor fixes to smartbulb docs [\#431](https://github.com/python-kasa/python-kasa/pull/431) (@rytilahti)
- Add a note that transition is not supported by all devices [\#398](https://github.com/python-kasa/python-kasa/pull/398) (@rytilahti)
- fix more outdated CLI examples, remove EP40 from bulb list [\#383](https://github.com/python-kasa/python-kasa/pull/383) (@HankB)
- Fix outdated smartstrip cli examples [\#382](https://github.com/python-kasa/python-kasa/pull/382) (@HankB)
- Add ToCs for doc pages [\#380](https://github.com/python-kasa/python-kasa/pull/380) (@rytilahti)
- Clarify information about supported devices [\#377](https://github.com/python-kasa/python-kasa/pull/377) (@rytilahti)
- Update README to add missing models and fix a link [\#351](https://github.com/python-kasa/python-kasa/pull/351) (@rytilahti)
- Add KP125 test fixture and support note. [\#350](https://github.com/python-kasa/python-kasa/pull/350) (@jalseth)

**Closed issues:**

- Add support for setting default behaviors for a soft or hard power on of the bulb [\#365](https://github.com/python-kasa/python-kasa/issues/365)

**Merged pull requests:**

- Some release preparation janitoring [\#432](https://github.com/python-kasa/python-kasa/pull/432) (@rytilahti)
- Bump certifi from 2021.10.8 to 2022.12.7 [\#409](https://github.com/python-kasa/python-kasa/pull/409) (@dependabot[bot])
- Add FUNDING.yml [\#402](https://github.com/python-kasa/python-kasa/pull/402) (@rytilahti)
- Update pre-commit hooks [\#401](https://github.com/python-kasa/python-kasa/pull/401) (@rytilahti)
- Update pre-commit url for flake8 [\#400](https://github.com/python-kasa/python-kasa/pull/400) (@rytilahti)
- Added .gitattributes file to retain LF only EOL markers when checking out on Windows [\#399](https://github.com/python-kasa/python-kasa/pull/399) (@jules43)
- Fix pytest warnings about asyncio [\#397](https://github.com/python-kasa/python-kasa/pull/397) (@jules43)
- Fix type hinting issue with call to click.Choice  [\#387](https://github.com/python-kasa/python-kasa/pull/387) (@jules43)
- Manually pass the codecov token in CI [\#378](https://github.com/python-kasa/python-kasa/pull/378) (@rytilahti)
- Correct typos in smartdevice.py [\#358](https://github.com/python-kasa/python-kasa/pull/358) (@felixonmars)
- Add fixtures for KS200M [\#356](https://github.com/python-kasa/python-kasa/pull/356) (@gritstub)
- Add fixtures for KS230 [\#355](https://github.com/python-kasa/python-kasa/pull/355) (@gritstub)
- Add fixtures for ES20M \(\#353\) [\#354](https://github.com/python-kasa/python-kasa/pull/354) (@gritstub)
- Add fixtures for KP100 [\#343](https://github.com/python-kasa/python-kasa/pull/343) (@bdraco)
- Add codeql checks [\#338](https://github.com/python-kasa/python-kasa/pull/338) (@rytilahti)

## [0.5.0](https://github.com/python-kasa/python-kasa/tree/0.5.0) (2022-04-24)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.4.3...0.5.0)

This is the first release of 0.5 series which includes converting the code base towards more modular approach where device-exposed modules (e.g., emeter, antitheft, or schedule) are implemented in their separate python modules to decouple them from the device-specific classes.

There should be no API breaking changes, but some previous issues hint that there may be as information from all supported modules are now requested during each update cycle (depending on the device type):
* Basic system info
* Emeter
* Time - properties (like `on_since`) use now time from the device for calculation to avoid jitter caused by different time between the host and the device
* Usage statistics - similar interface to emeter, but reports on-time statistics instead of energy consumption (new)
* Countdown (new)
* Antitheft (new)
* Schedule (new)
* Motion - for configuring motion settings on some dimmers (new)
* Ambientlight - for configuring brightness limits when motion sensor actuates on some dimmers (new)
* Cloud - information about cloud connectivity (new)

For developers, the new functionalities are currently only exposed through the implementation modules accessible through `modules` property.
Pull requests improving the functionality of modules as well as adding better interfaces to device classes are welcome!

**Breaking changes:**

- Drop deprecated, type-specific options in favor of --type [\#336](https://github.com/python-kasa/python-kasa/pull/336) (@rytilahti)
- Convert the codebase to be more modular [\#299](https://github.com/python-kasa/python-kasa/pull/299) (@rytilahti)

**Implemented enhancements:**

- Improve HS220 support [\#44](https://github.com/python-kasa/python-kasa/issues/44)

**Fixed bugs:**

- Skip running discovery on --help on subcommands [\#122](https://github.com/python-kasa/python-kasa/issues/122)
- Avoid retrying open\_connection on unrecoverable errors [\#340](https://github.com/python-kasa/python-kasa/pull/340) (@bdraco)
- Avoid discovery on --help [\#335](https://github.com/python-kasa/python-kasa/pull/335) (@rytilahti)

**Documentation updates:**

- Trying to poll device every 5 seconds but getting asyncio errors [\#316](https://github.com/python-kasa/python-kasa/issues/316)
- Docs: Smart Strip - Emeter feature  Note  [\#257](https://github.com/python-kasa/python-kasa/issues/257)
- Documentation addition: Smartplug access to internet ntp server pool. [\#129](https://github.com/python-kasa/python-kasa/issues/129)
- Export modules & make sphinx happy [\#334](https://github.com/python-kasa/python-kasa/pull/334) (@rytilahti)
- Various documentation updates [\#333](https://github.com/python-kasa/python-kasa/pull/333) (@rytilahti)

**Merged pull requests:**

- Add fixtures for kl420 [\#339](https://github.com/python-kasa/python-kasa/pull/339) (@bdraco)

## [0.4.3](https://github.com/python-kasa/python-kasa/tree/0.4.3) (2022-04-05)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.4.2...0.4.3)

**Fixed bugs:**

- Divide by zero when HS300 powerstrip is discovered [\#292](https://github.com/python-kasa/python-kasa/issues/292)
- Ensure bulb state is restored when turning back on [\#330](https://github.com/python-kasa/python-kasa/pull/330) (@bdraco)

**Merged pull requests:**

- Update pre-commit hooks to fix black in CI [\#331](https://github.com/python-kasa/python-kasa/pull/331) (@rytilahti)
- Fix test\_deprecated\_type stalling [\#325](https://github.com/python-kasa/python-kasa/pull/325) (@bdraco)

## [0.4.2](https://github.com/python-kasa/python-kasa/tree/0.4.2) (2022-03-21)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.4.1...0.4.2)

**Implemented enhancements:**

- Allow environment variables for discovery target, device type and debug [\#313](https://github.com/python-kasa/python-kasa/pull/313) (@rytilahti)
- Add 'internal\_state' to return the results from the last update query [\#306](https://github.com/python-kasa/python-kasa/pull/306) (@rytilahti)
- Drop microsecond precision for on\_since [\#296](https://github.com/python-kasa/python-kasa/pull/296) (@rytilahti)
- Add effect support for light strips [\#293](https://github.com/python-kasa/python-kasa/pull/293) (@bdraco)

**Fixed bugs:**

- TypeError: \_\_init\_\_\(\) got an unexpected keyword argument 'package\_name' [\#311](https://github.com/python-kasa/python-kasa/issues/311)
- RuntimeError: Event loop is closed on WSL [\#294](https://github.com/python-kasa/python-kasa/issues/294)
- Don't crash on devices not reporting features [\#317](https://github.com/python-kasa/python-kasa/pull/317) (@rytilahti)

**Merged pull requests:**

- Add pyupgrade to CI runs [\#314](https://github.com/python-kasa/python-kasa/pull/314) (@rytilahti)
- Depend on asyncclick \>= 8 [\#312](https://github.com/python-kasa/python-kasa/pull/312) (@rytilahti)
- Guard emeter accesses to avoid keyerrors [\#304](https://github.com/python-kasa/python-kasa/pull/304) (@rytilahti)
- cli: cleanup discover, fetch update prior device access [\#303](https://github.com/python-kasa/python-kasa/pull/303) (@rytilahti)
- Fix unsafe \_\_del\_\_ in TPLinkSmartHomeProtocol [\#300](https://github.com/python-kasa/python-kasa/pull/300) (@bdraco)
- Improve typing for protocol class [\#289](https://github.com/python-kasa/python-kasa/pull/289) (@rytilahti)
- Added a fixture file for KS220M [\#273](https://github.com/python-kasa/python-kasa/pull/273) (@mrbetta)

## [0.4.1](https://github.com/python-kasa/python-kasa/tree/0.4.1) (2022-01-14)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.4.0...0.4.1)

**Implemented enhancements:**

- Add --type option to cli [\#269](https://github.com/python-kasa/python-kasa/pull/269) (@rytilahti)
- Minor improvements to onboarding doc [\#264](https://github.com/python-kasa/python-kasa/pull/264) (@rytilahti)
- Add fixture file for KL135 [\#263](https://github.com/python-kasa/python-kasa/pull/263) (@ErikSGross)
- Add KL135 color temperature range [\#256](https://github.com/python-kasa/python-kasa/pull/256) (@rytilahti)
- Add py.typed to flag that the package is typed [\#251](https://github.com/python-kasa/python-kasa/pull/251) (@rytilahti)
- Add script to check supported devices, update README [\#242](https://github.com/python-kasa/python-kasa/pull/242) (@rytilahti)
- Add perftest to devtools [\#236](https://github.com/python-kasa/python-kasa/pull/236) (@rytilahti)
- Add KP401 US fixture [\#234](https://github.com/python-kasa/python-kasa/pull/234) (@bdraco)
- Add KL60 US KP105 UK fixture [\#233](https://github.com/python-kasa/python-kasa/pull/233) (@bdraco)
- Make cli interface more consistent [\#232](https://github.com/python-kasa/python-kasa/pull/232) (@rytilahti)
- Add KL400, KL50 fixtures [\#231](https://github.com/python-kasa/python-kasa/pull/231) (@bdraco)
- Add fixture for newer KP400 firmware [\#227](https://github.com/python-kasa/python-kasa/pull/227) (@bdraco)
- Switch to poetry-core [\#226](https://github.com/python-kasa/python-kasa/pull/226) (@fabaff)
- Add fixtures for LB110, KL110, EP40, KL430, KP115 [\#224](https://github.com/python-kasa/python-kasa/pull/224) (@bdraco)

**Fixed bugs:**

- Discovery on WSL results in OSError: \[Errno 22\] Invalid argument [\#246](https://github.com/python-kasa/python-kasa/issues/246)
- New firmware for HS103 blocking local access? [\#42](https://github.com/python-kasa/python-kasa/issues/42)
- Pin mistune to \<2.0.0 to fix doc builds [\#270](https://github.com/python-kasa/python-kasa/pull/270) (@rytilahti)
- Catch exceptions raised on unknown devices during discovery [\#240](https://github.com/python-kasa/python-kasa/pull/240) (@rytilahti)

**Merged pull requests:**

- Publish to pypi on github release published [\#287](https://github.com/python-kasa/python-kasa/pull/287) (@rytilahti)
- Relax asyncclick version requirement [\#286](https://github.com/python-kasa/python-kasa/pull/286) (@rytilahti)
- Do not crash on discovery on WSL [\#283](https://github.com/python-kasa/python-kasa/pull/283) (@rytilahti)
- Add python 3.10 to CI [\#279](https://github.com/python-kasa/python-kasa/pull/279) (@rytilahti)
- Use codecov-action@v2 for CI [\#277](https://github.com/python-kasa/python-kasa/pull/277) (@rytilahti)
- Add coverage\[toml\] dependency to fix coverage on CI [\#271](https://github.com/python-kasa/python-kasa/pull/271) (@rytilahti)
- Allow publish on test pypi workflow to fail [\#248](https://github.com/python-kasa/python-kasa/pull/248) (@rytilahti)

## [0.4.0](https://github.com/python-kasa/python-kasa/tree/0.4.0) (2021-09-27)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.4.0.pre0...0.4.0)

**Implemented enhancements:**

- KL430 support [\#67](https://github.com/python-kasa/python-kasa/issues/67)
- Improve retry logic for discovery, messaging \(was: Handle empty responses\) [\#38](https://github.com/python-kasa/python-kasa/issues/38)
- Fix lock being unexpectedly reset on close [\#218](https://github.com/python-kasa/python-kasa/pull/218) (@bdraco)
- Avoid calling pformat unless debug logging is enabled [\#217](https://github.com/python-kasa/python-kasa/pull/217) (@bdraco)
- Keep connection open and lock to prevent duplicate requests [\#213](https://github.com/python-kasa/python-kasa/pull/213) (@bdraco)
- Improve emeterstatus API, move into own module [\#205](https://github.com/python-kasa/python-kasa/pull/205) (@rytilahti)
- Avoid temp array during encrypt and decrypt [\#204](https://github.com/python-kasa/python-kasa/pull/204) (@bdraco)
- Add emeter support for strip sockets [\#203](https://github.com/python-kasa/python-kasa/pull/203) (@bdraco)
- Add own device type for smartstrip children [\#201](https://github.com/python-kasa/python-kasa/pull/201) (@rytilahti)
- bulb: allow set\_hsv without v, add fallback ct range [\#200](https://github.com/python-kasa/python-kasa/pull/200) (@rytilahti)
- Improve bulb support \(alias, time settings\) [\#198](https://github.com/python-kasa/python-kasa/pull/198) (@rytilahti)
- Improve testing harness to allow tests on real devices [\#197](https://github.com/python-kasa/python-kasa/pull/197) (@rytilahti)
- cli: add human-friendly printout when calling temperature on non-supported devices [\#196](https://github.com/python-kasa/python-kasa/pull/196) (@JaydenRA)
- 'Interface' parameter added to discovery process [\#79](https://github.com/python-kasa/python-kasa/pull/79) (@dmitryelj)
- Add support for lightstrips \(KL430\) [\#74](https://github.com/python-kasa/python-kasa/pull/74) (@rytilahti)

**Fixed bugs:**

- KL430: Throw error for Device specific information [\#189](https://github.com/python-kasa/python-kasa/issues/189)
- `Unable to find a value for 'current'` error when attempting to query KL125 bulb emeter [\#142](https://github.com/python-kasa/python-kasa/issues/142)
- `Unknown color temperature range` error when attempting to query KL125 bulb state [\#141](https://github.com/python-kasa/python-kasa/issues/141)
- HS300 Children plugs have emeter [\#64](https://github.com/python-kasa/python-kasa/issues/64)
- dump\_devinfo: handle latitude/longitude keys properly [\#175](https://github.com/python-kasa/python-kasa/pull/175) (@rytilahti)
- Simplify discovery query, refactor dump-devinfo [\#147](https://github.com/python-kasa/python-kasa/pull/147) (@rytilahti)
- Return None instead of raising an exception on missing, valid emeter keys [\#146](https://github.com/python-kasa/python-kasa/pull/146) (@rytilahti)
- Simplify device class detection for discovery, fix hardcoded timeout [\#112](https://github.com/python-kasa/python-kasa/pull/112) (@rytilahti)
- Update cli.py to addresss crash on year/month calls and improve output formatting [\#103](https://github.com/python-kasa/python-kasa/pull/103) (@BuongiornoTexas)

**Documentation updates:**

- Discover does not support specifying network interface [\#167](https://github.com/python-kasa/python-kasa/issues/167)
- Add ability to control individual sockets on KP400 [\#121](https://github.com/python-kasa/python-kasa/issues/121)
- Improve poetry usage documentation [\#60](https://github.com/python-kasa/python-kasa/issues/60)
- Improve cli documentation for bulbs and power strips [\#123](https://github.com/python-kasa/python-kasa/pull/123) (@rytilahti)

**Project maintenance:**

- Add HS220 hw 2.0 fixture [\#107](https://github.com/python-kasa/python-kasa/pull/107) (@appleguru)

**Merged pull requests:**

- Add github workflow for pypi publishing [\#220](https://github.com/python-kasa/python-kasa/pull/220) (@rytilahti)
- Add host information to protocol debug logs [\#219](https://github.com/python-kasa/python-kasa/pull/219) (@rytilahti)
- Add KL130 fixture, initial lightstrip tests [\#214](https://github.com/python-kasa/python-kasa/pull/214) (@rytilahti)
- Cleanup discovery & add tests [\#212](https://github.com/python-kasa/python-kasa/pull/212) (@rytilahti)
- More CI fixes [\#208](https://github.com/python-kasa/python-kasa/pull/208) (@rytilahti)
- Fix CI dep installation [\#207](https://github.com/python-kasa/python-kasa/pull/207) (@rytilahti)
- Use github actions instead of azure pipelines [\#206](https://github.com/python-kasa/python-kasa/pull/206) (@rytilahti)
- Add KP115 fixture [\#202](https://github.com/python-kasa/python-kasa/pull/202) (@rytilahti)
- Perform initial update only using the sysinfo query [\#199](https://github.com/python-kasa/python-kasa/pull/199) (@rytilahti)
- Add real kasa KL430\(UN\) device dump [\#192](https://github.com/python-kasa/python-kasa/pull/192) (@iprodanovbg)
- Use less strict matcher for kl430 color temperature [\#190](https://github.com/python-kasa/python-kasa/pull/190) (@rytilahti)
- Add EP10\(US\) 1.0 1.0.2 fixture [\#174](https://github.com/python-kasa/python-kasa/pull/174) (@nbrew)
- Add a note about using the discovery target parameter [\#168](https://github.com/python-kasa/python-kasa/pull/168) (@leandroreox)
- Simplify mac address handling [\#162](https://github.com/python-kasa/python-kasa/pull/162) (@rytilahti)
- Added KL125 and HS200 fixture dumps and updated tests to run on new format [\#160](https://github.com/python-kasa/python-kasa/pull/160) (@brianthedavis)
- Add KL125 bulb definition [\#143](https://github.com/python-kasa/python-kasa/pull/143) (@mdarnol)
- README.md: Add link to MQTT interface for python-kasa [\#140](https://github.com/python-kasa/python-kasa/pull/140) (@flavio-fernandes)
- Fix documentation on Smart strips [\#136](https://github.com/python-kasa/python-kasa/pull/136) (@flavio-fernandes)
- add tapo link, fix tplink-smarthome-simulator link [\#133](https://github.com/python-kasa/python-kasa/pull/133) (@rytilahti)
- Leverage data from UDP discovery to initialize device structure [\#132](https://github.com/python-kasa/python-kasa/pull/132) (@dlee1j1)
- Pin dependencies on major versions, add poetry.lock [\#94](https://github.com/python-kasa/python-kasa/pull/94) (@rytilahti)
- add a small example script to show library usage [\#90](https://github.com/python-kasa/python-kasa/pull/90) (@rytilahti)
- add .readthedocs.yml required for poetry builds [\#89](https://github.com/python-kasa/python-kasa/pull/89) (@rytilahti)
- Improve installation instructions [\#86](https://github.com/python-kasa/python-kasa/pull/86) (@rytilahti)
- cli: Fix incorrect use of asyncio.run for temperature command [\#85](https://github.com/python-kasa/python-kasa/pull/85) (@rytilahti)
- Add parse\_pcap to devtools, improve readme on contributing [\#84](https://github.com/python-kasa/python-kasa/pull/84) (@rytilahti)
- Add --transition to bulb-specific cli commands, fix turn\_{on,off} signatures [\#81](https://github.com/python-kasa/python-kasa/pull/81) (@rytilahti)
- Improve bulb API, force turn on for all light changes as offline changes are not supported [\#76](https://github.com/python-kasa/python-kasa/pull/76) (@rytilahti)
- Simplify API documentation by using doctests [\#73](https://github.com/python-kasa/python-kasa/pull/73) (@rytilahti)
- Bulbs: allow specifying transition for state changes [\#70](https://github.com/python-kasa/python-kasa/pull/70) (@rytilahti)
- Add transition support for SmartDimmer [\#69](https://github.com/python-kasa/python-kasa/pull/69) (@connorproctor)

## [0.4.0.pre0](https://github.com/python-kasa/python-kasa/tree/0.4.0.pre0) (2020-05-27)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.3.5...0.4.0.pre0)

**Implemented enhancements:**

- Add commands to control the wifi settings [\#45](https://github.com/python-kasa/python-kasa/pull/45) (@rytilahti)

**Fixed bugs:**

- HSV cli command not working [\#43](https://github.com/python-kasa/python-kasa/issues/43)

**Merged pull requests:**

- Add retries to protocol queries [\#65](https://github.com/python-kasa/python-kasa/pull/65) (@rytilahti)
- General cleanups all around \(janitoring\) [\#63](https://github.com/python-kasa/python-kasa/pull/63) (@rytilahti)
- Improve dimmer support [\#62](https://github.com/python-kasa/python-kasa/pull/62) (@rytilahti)
- Optimize I/O access [\#59](https://github.com/python-kasa/python-kasa/pull/59) (@rytilahti)
- Remove unnecessary f-string definition to make tests pass [\#58](https://github.com/python-kasa/python-kasa/pull/58) (@rytilahti)
- Convert to use poetry & pyproject.toml for dep & build management [\#54](https://github.com/python-kasa/python-kasa/pull/54) (@rytilahti)
- Add fixture for KL60 [\#52](https://github.com/python-kasa/python-kasa/pull/52) (@rytilahti)
- Ignore D202 where necessary [\#50](https://github.com/python-kasa/python-kasa/pull/50) (@rytilahti)
- Support wifi scan & join for bulbs using a different interface [\#49](https://github.com/python-kasa/python-kasa/pull/49) (@rytilahti)
- Return on\_since only when its available and the device is on [\#48](https://github.com/python-kasa/python-kasa/pull/48) (@rytilahti)
- Allow 0 brightness for smartdimmer [\#47](https://github.com/python-kasa/python-kasa/pull/47) (@rytilahti)
- async++, small powerstrip improvements [\#46](https://github.com/python-kasa/python-kasa/pull/46) (@rytilahti)
- Check for emeter support on power strips/multiple plug outlets [\#41](https://github.com/python-kasa/python-kasa/pull/41) (@acmay)
- Remove unnecessary cache [\#40](https://github.com/python-kasa/python-kasa/pull/40) (@rytilahti)
- Add in some new device types [\#39](https://github.com/python-kasa/python-kasa/pull/39) (@acmay)
- Add test fixture for KL130 [\#35](https://github.com/python-kasa/python-kasa/pull/35) (@bdraco)
- Move dimmer support to its own class [\#34](https://github.com/python-kasa/python-kasa/pull/34) (@rytilahti)
- Fix azure pipeline badge [\#32](https://github.com/python-kasa/python-kasa/pull/32) (@rytilahti)
- Enable Windows & OSX builds [\#31](https://github.com/python-kasa/python-kasa/pull/31) (@rytilahti)
- Depend on py3.7+ for tox, add python 3.8 to azure pipeline targets [\#29](https://github.com/python-kasa/python-kasa/pull/29) (@rytilahti)
- Add KP303 to the list of powerstrips [\#28](https://github.com/python-kasa/python-kasa/pull/28) (@rytilahti)
- Move child socket handling to its own SmartStripPlug class [\#26](https://github.com/python-kasa/python-kasa/pull/26) (@rytilahti)
- Adding KP303 to supported devices [\#25](https://github.com/python-kasa/python-kasa/pull/25) (@epicalex)
- use pytestmark to avoid repeating asyncio mark [\#24](https://github.com/python-kasa/python-kasa/pull/24) (@rytilahti)
- Cleanup constructors by removing ioloop and protocol arguments [\#23](https://github.com/python-kasa/python-kasa/pull/23) (@rytilahti)
- Add \(some\) tests to the cli tool [\#22](https://github.com/python-kasa/python-kasa/pull/22) (@rytilahti)
- Test against the newly added device fixtures  [\#21](https://github.com/python-kasa/python-kasa/pull/21) (@rytilahti)
- move testing reqs to requirements\_test.txt, add pytest-asyncio for pipelines [\#20](https://github.com/python-kasa/python-kasa/pull/20) (@rytilahti)
- Remove unused save option and add scrubbing [\#19](https://github.com/python-kasa/python-kasa/pull/19) (@TheGardenMonkey)
- Add real kasa device dumps [\#18](https://github.com/python-kasa/python-kasa/pull/18) (@TheGardenMonkey)
- Fix dump-discover to use asyncio.run [\#16](https://github.com/python-kasa/python-kasa/pull/16) (@rytilahti)
- Add device\_id property, rename context to child\_id [\#15](https://github.com/python-kasa/python-kasa/pull/15) (@rytilahti)
- Remove sync interface, add asyncio discovery [\#14](https://github.com/python-kasa/python-kasa/pull/14) (@rytilahti)
- Remove --ip which was just an alias to --host [\#6](https://github.com/python-kasa/python-kasa/pull/6) (@rytilahti)
- Set minimum requirement to python 3.7 [\#5](https://github.com/python-kasa/python-kasa/pull/5) (@rytilahti)
- change ID of Azure Pipeline [\#3](https://github.com/python-kasa/python-kasa/pull/3) (@basnijholt)
- Mass rename to \(python-\)kasa [\#1](https://github.com/python-kasa/python-kasa/pull/1) (@rytilahti)

Historical pyHS100 changelog
============================

0.3.5 (2019-04-13)
------------

- Fix for SmartStrip repr (#169) [Alex]

  * Added unit tests for repr.

  * Fix repr for SmartStrip.

  Fixes #165

- Smartstrip: return on_since state information only when the socket is on (#161) [Teemu R]

  * Smartstrip: return on_since state information only when the socket is on

  Fixes #160

  * add proper cli printout for hs300 child sockets

  * iterate over range, not an integer

- Bulb: add the temperature range to state_information, inform the user if the info is missing when calling temperature (#163) [Teemu R]

- Fix Discover#discover incorrect documentation (#159) [Georgi Kirichkov]

  The documentation states the timeout defaults to 5 seconds, but in the definition of the method timeout is set to 3

- Add kelvin range for KL130 (#156) [dieselrabbit]

  * Add kelvin range for KL130 (new color bulb)

  * Add kelvin range for KL120

  Unable to test this personally as I don't have this bulb.

- Add LB230. [Teemu R]

  Works according to https://github.com/home-assistant/home-assistant.io/pull/8090

- Add KL series of bulbs. [Teemu R]

  works according to https://github.com/home-assistant/home-assistant.io/pull/8134


0.3.4 (2019-01-16)
------------

There are two notable changes (and other small fixes) in this minor release thanks to our contributors:

* Support for HS300 smartstrip (thanks to jimboca!)
* The hue range for light bulbs is fixed (thanks to nkonopinski, Annika Jacobs and Joe Zach!)


- Updated valid range to 360 (with passing tests) (#153) [Annika Jacobs, Zac Koch]

  * Updated valid range to 360

  with it set to 359 it will not show the color red. Just tested this with a buddies bulb - same model/fw
  https://imgur.com/a/kSNZIuL

- Add support for HS300 power strip (#137) [jimboca]

- Add HS103 to readme. [Teemu R]

- Avoid 'referenced before assignment' exception (#150) [Kevron Rees]

- Cli: show an error for incorrect hsv values (#142) [Annika Jacobs]

  Raising an exception if an incomplete HSV colour is provided.

- Add a "Reviewed by Hound" badge (#139) [Scott Albertson]

- Change valid hue range to 0-359 (fixes #130), update README.md & test
  (#140) [Annika Jacobs, nkonopinski]

  Tested on LB130(EU) hardware 1.0, firmware 1.8.6 Build 180809 Rel.091659

- Remove deprecated identify, this has been deprecated for long enough.
  (#136) [Teemu R]

  * Remove deprecated identify, this has been deprecated for long enough.

- Add missed test for invalid types. [Teemu R]

- Update README to include mention about hs220. [Teemu R]

- Add tests and pretty output for HS220, fix minor issues in tests.
  [Teemu R]

- Add reboot command to restart the device (#129) [Teemu R]


0.3.3 (2018-09-06)
------------------

This release contains a breaking change for hsv setter, which is changed to accept
the new brightness value in percentage instead of an integer between 1 and 255.

The alias support has been extended to allow changing the alias, as well as accessing
the device using it (without specifying an IP address or a hostname), which can be
useful in some setups. Furthermore utf8-encoded aliases are now handled correctly.

- Fix bug that changed brightness at each HSV update (#124) [Sebastian Templ]

  * Fix bug that changed brightness at each hsv update

  The HSV setter should accept a percentage for the brightness
  value but actually assumed the brightness to be in absolute values
  between 1 and 255.
  This resulted in brightness reductions at each HSV update, in
  steps of 100% -> 100/255=39% -> 39/255=15% -> ... (see also
  https://github.com/home-assistant/home-assistant/issues/15582,
  where I originally reported this bug).

  * Modify HSV property to return brightness in percent

  Switch from reported brightness values of 1..255 to percentage
  values, for consistency with the apidoc and 8761dd8.

  * Add checks and tests for the hsv setter

  - make sure that new (hue, saturation, brightness) values are
    within their valid ranges (0..255, 0..100, 0..100) and raise
    SmartDeviceException if they are not
  - add test function for the hsv setter

- Allow using alias instead of IP address or hostname (#127) [kwazel]

  * Added option to control devices by device name

  * set unused ip address to dont-care

  * spend less time discovering by devicename, removed command

  * consistent use of alias instead of device name

  * processed review comments

  * Return when no device with alias has been found

- Add 'alias' command for querying and setting the alias (#126) [Teemu R]

  * add 'alias' command for querying and setting the alias

  * calculate coverage only on library files, e.g., ignoring cli and test files

  * remove py34 and add py37

  * readd py33, remove it from travis as it seems to be a travis limitation only

  * use xenial dist for travis, regular does not support py37..

- Support Unicode strings in encrypt/decrypt (#125) [Anders Melchiorsen]


0.3.2 (2018-06-17)
------------------

- Add bulb valid temperature range (#122) [Thibault Cohen]


0.3.1 (2018-06-16)
------------------

This release adds a few improvements, most importantly:

* emeter support for new HS110 hardware/firmware revision.

* HS220 supports now dimming.

Breaking changes:

* get_emeter_daily & get_emeter_monthly will report back in kwh on bulbs, making the API consistent with the smart plugs.

- Fix emeter support for newer HS110 firmwares (#107) [Teemu R]

  * Add support for new-style emeter

  This commit adds a straightforward dict-extending container,
  which converts between the old and new keys of the get_emeter_realtime()
  Furthermore the unit tests are converted to base on HS100
  instead of HS110.

  This is the first step to fix #103, other emeter-using functionality
  has not yet been converted, only getting the current consumption.

  * fix a couple of linting issues

  * Convert new-style emeter values also for get_emeter_daily() and get_emeter_monthly()

  * Adds a new 'kwh' parameter for those calls, which defaults to True
  * This changes the behavior of bulbs emeter reporting, use False if you prefer the preciser values

- Update pypi description (#102) [Teemu R]

  * update pypi description

  * add wall switches

- Update smartplug.py to support dimming in HS220 (#115) [JsChiSurf]

  * Update smartplug.py to support dimming in HS220

  Switch functions essentially as a "plug" with the addition to support for dimming, for which can be test for by verifying existence of
'brightness' array value.

  * Attempt at updates to pass validator

  * Maybe this time?  :-)

  * Add more detail to comment blocks

  Make clear in requests for current brightness level the expected return values, and note that light will turn on when setting a brightness
level, if not already on.  This makes clear that a state change request (turn_on) does NOT have to be made first when setting brightness.

  * Update smartplug.py

  * Update smartplug.py

  Fixes #114

- Add python_requires for >= 3.4. [Teemu Rytilahti]

- Add hs210. [Teemu R]

  Based on user report: https://community.home-assistant.io/t/tp-link-hs210-3-way-kit/39762/6

- Add support for DNS host names (#104) [K Henriksson]

- Use direct device type discovery for devices (#106) [K Henriksson]

  This is more efficient than enumerating all devices and checking the IP.

- Cli: add 'time' command to get the current time from the device.
  [Teemu Rytilahti]

- Created a docker file to aid dev setup (#99) [TheSmokingGnu]

  * created a docker file to aid dev setup

  * fixed review comments in README and Dockerfile

  * review comments to simplify the docker run command


0.3.0 (2017-09-14)
------------------

This is the first release after a while and aims to improve the robustness all-around.
To make this happen we have decided to break the API and drop the support for Python 2.

API break:
    * Python2 support has been dropped.
    * pyHS100/pyHS100.py has been splitted to smartdevice.py, smartplug.py and smartbulb.py, no one should have ever accessed these directly though.
    * SmartPlugException is no more, SmartDeviceException is used by both SmartPlug and SmartBulb
    * Discovery has been moved from TPLinkSmartHomeProtocol into its own class for easier 3rd party use.
    * SmartDevice's identify() and `features` will emit a warning when used. These will likely be dropped or revised in the future and their use should be avoided.

Other changes:

    * CLI tool supports device discovery and is usable without specifying device type or IP for testing
    * CLI tool supports changing bulb-specific settings
    * Library support & unit tests are extended to cover more devices.
       - Supported plugs: HS100, HS105, HS110
       - Supported switches: HS200
       - Supported bulbs: LB100, LB110, LB120, LB130

- Bump the version. [Teemu Rytilahti]

- Revise README, fixes #86. [Teemu Rytilahti]

- Update the changelog. [Teemu Rytilahti]

- Local test clean (#96) [Sean Gollschewsky]

  * Add ignores for working coverage/tox/IDE files.

  * Allow tox not to fail if python version is not available.

- Move SmartDeviceException to SmartDevice, and remove types.py complet…
  (#95) [Teemu R]

  * move SmartDeviceException to SmartDevice, and remove types.py completely. fixes #94

  * do not import skipIf anymore

- Move has_emeter implementation from SmartDevice to SmartPlug, avoid
  using features() internally (#93) [Teemu R]

  * move has_emeter implementation from SmartDevice to SmartPlug, avoid using features() internally

  * add stacklevel to deprecation warnings to see where they are really called

  * make tests pass on a real device. if PLUG_IP is not None, the tests will be run on a device at the defined IP address

- Add typing hints to make it easier for 3rd party developers to use the
  library (#90) [Teemu R]

  * add typing hints to make it easier for 3rd party developers to use the library

  * remove unused devicetype enum to support python3.3

  * add python 3.3 to travis and tox, install typing module in setup.py
- Execute coveralls only on travis, fixes #84 (#91) [Teemu R]

- Make flake8 pass by some rewording. [Teemu Rytilahti]

- Make hound a bit more happier. [Teemu Rytilahti]

- Deprecate features and identify, use state_information in __repr__ instead of identify. [Teemu Rytilahti]

- Fix smartbulb hsv documentation, values are degrees and percentages instead of 0-255. [Teemu Rytilahti]

- Another try, just with module name. [Teemu Rytilahti]

- Make tox run pytest-cov, add coveralls. [Teemu Rytilahti]

- Prevent failure if device's sysinfo does not have a "feature" attribute. (#77) [Sean Gollschewsky]

- Allow None for rssi, add a missing newline to fakes.py. [Teemu Rytilahti]

- Add hs100 tests. [Teemu Rytilahti]

- Make tests to test against all known device variants. [Teemu Rytilahti]

- Remove unused tplinksmarthomeprotocol import. [Teemu Rytilahti]

- Fix hs105 mac to pass the test, wrap sysinfo_lb110 properly inside 'system' [Teemu Rytilahti]

- Return None instead of False for emeter related actions. [Teemu Rytilahti]

- Wrap sysinfo to defaultdict to return None for keys which do not exist, makes unsupported keys not to fail hard (#72) [Teemu R]

- Add hs100 example to fakes.py, thanks to Semant1ka on #67 (#74) [Teemu R]

- Discover refactoring, enhancements to the cli tool (#71) [Teemu R]

  * Discover refactoring, enhancements to the cli tool

  * Discover tries to detect the type of the device from sysinfo response
  * Discover.discover() returns an IP address keyed dictionary,
    values are initialized instances of the automatically detected device type.

  * When no IP is given, autodetect all supported devices and print out their states
  * When only IP but no type is given, autodetect type and make a call based on that information.
    * One can define --bulb or --plug to skip the detection.

  * renamed pyHS100.py -> smartdevice.py

  * SmartPlugException -> SmartDeviceException in comments

  * fix mic_type check

  * make time() return None on failure as we don't know which devices support getting the time and it's used in the cli tool

  * hw_info: check if key exists before accessing it, add mic_mac and mic_type

  * Check for mic_mac on mac, based on work by kdschloesser on issue #59

  * make hound happy, __init__ on SmartDevice cannot error out so removing 'raises' documentation

- Add LB110 sysinfo (#75) [Sean Gollschewsky]

  * Add LB110 sysinfo

  * Linting.

- Add @pass_dev to hsv, adjust ranges (#70) [Teemu R]

  * add @pass_dev to hsv command, it was always broken

  * Hue goes up to 360, saturation and value are up to 100(%)

- Extract shared types (exceptions, enums), add module level doc, rename exception to be generic. [Teemu Rytilahti]

- Add check to ensure devices with lat/lon with `_i` suffix are supported (#54) (#56) [Matt LeBrun]

  * Add check to ensure devices with lat/lon with `_i` suffix are supported (#54)

  * Add .gitignore for posterity

- Generalize smartdevice class and add bulb support for the cli tool (#50) [Teemu R]

  Fixes #48 and #51. The basic functionality should work on all types of supported devices, for bulb specific commands it is currently necessary to specify ```--bulb```.

- Refactor and drop py2 support (#49) [Teemu R]

  * move is_off property to SmartDevice, implement is_on for bulb and use it

  * refactor by moving smartbulb and smartplug to their own classes

  * drop python2 compatibility, make flake8 happy

  * travis: remove 2.7, add 3.6

0.2.4.2 (2017-04-08)
--------------------
- Add installation requirement for future package. [Teemu Rytilahti]

0.2.4.1 (2017-03-26)
--------------------
- Cli: display an error if no ip is given. [Teemu Rytilahti]


0.2.4 (2017-03-26)
------------------

- Add new client tool (#42) [Teemu R]

  * Add new client tool

  After installing the package pyhs100 command-line tool can be used
  to control the plug.

  See --help for its usage, most of the features for plugs are implemented,
  some of the shared functionality works for bulbs too.

  * Add discover command

  * Delete old examples, the cli works as an example well enough

- Ignore OSError on socket.shutdown() [Teemu Rytilahti]

  This fixes #22 and obsoletes PR #23.
- Set color temp to 0 when trying to change color (#36) [pete1450]

  * set color temp to 0 when trying to change color

  * changed tabs to spaces

- Add changelog & add .gitchangelog.rc (#28) [Teemu R]

  This commits adds .gitchangelog.rc for changelog generation.
  To generate, simply run gitchangelog.

- Discover: Catch socket.timeout and debug log it (#34) [Teemu R]

  Fixes #33

- Add flake8 to tox, disable qa on pyHS100/__init__.py, fix py27
  compatibility (#31) [Teemu R]

- Add support for TP-Link smartbulbs (#30) [Matthew Garrett]

  * Add support for new-style protocol

  Newer devices (including my LB130) seem to include the request length in
  the previously empty message header, and ignore requests that lack it. They
  also don't send an empty packet as the final part of a response, which can
  lead to hangs. Add support for this, with luck not breaking existing devices
  in the process.

  * Fix tests

  We now include the request length in the encrypted packet header, so strip
  the header rather than assuming that it's just zeroes.

  * Create a SmartDevice parent class

  Add a generic SmartDevice class that SmartPlug can inherit from, in
  preparation for adding support for other device types.

  * Add support for TP-Link smartbulbs

  These bulbs use the same protocol as the smart plugs, but have additional
  commands for controlling bulb-specific features. In addition, the bulbs
  have their emeter under a different target and return responses that
  include the energy unit in the key names.

  * Add tests for bulbs

  Not entirely comprehensive, but has pretty much the same level of testing
  as plugs


0.2.3 (2017-01-11)
------------------

- Add .gitchnagelog.rc for changelog generation. to generate, simply
  install and run gitchangelog. [Teemu Rytilahti]

- Version bump. [GadgetReactor]

- Initial steps to remove caching (#26) [Teemu R]

  This commit removes caching of sysinfo to avoid
  inconsistent states as described in issue #14.

  Each an every access for properties will cause a request
  to be made to the device. To avoid this, user of the library
  may want to access sys_info() directly instead of using the helpers.

  Currently sys_info() returns raw json object where-as helpers do
  parse information for easier consumption; current state is just to
  provide a PoC how it looks compared to having an active update()
  for fetching the info.

- Make tests runnable without device (#24) [Teemu R]

  * Make tests runnable without device

  Adds preliminary support for fake devices, thanks to
  hoveeman's sysinfos from issue #14,
  making running tests possible without a device.

  At the moment we have only HS110 and HS200 infos available, and tests
  are currently run only against HS110 data.

  * Make tests py27 compatible

- Add device discovery (#25) [Teemu R]

  * add (untested) discover mode

  * Keep discovery and normal communication separate, uppercase magic consts

  This sepearates the earlier test code for discovering devices,
  and adds 5 sec timeout for gathering responses from potential devices.

  This commit also uppercases magic constants.

  Discovery & communication tested with HS110.

  * update readme with example how to discover devices, pep8ify

- Add timeout to query (#19) [Austin]

- Refactor & add unittests for almost all functionality, add tox for
  running tests on py27 and py35 (#17) [Teemu R]

  * Refactor & add unittests for almost all functionality, add tox for running tests on py27 and py35

  This commit adds unit tests for current api functionality.
  - currently no mocking, all tests are run on the device.
  - the library is now compatible with python 2.7 and python 3.5, use tox for tests
  - schema checks are done with voluptuous

  refactoring:
  - protocol is separated into its own file, smartplug adapted to receive protocol worker as parameter.
  - cleaned up the initialization routine, initialization is done on use, not on creation of smartplug
  - added model and features properties, identity kept for backwards compatibility
  - no more storing of local variables outside _sys_info, paves a way to handle state changes sanely (without complete reinitialization)

  * Fix CI warnings, remove unused leftover code

  * Rename _initialize to _fetch_sysinfo, as that's what it does.

  * examples.cli: fix identify call, prettyprint sysinfo, update readme which had false format for led setting

  * Add tox-travis for automated testing.

0.2.2 (2016-12-13)
------------------

- Version bump (#16) [Georgi Kirichkov]

- Read all data from the device, disable double-encoding, implement more
  APIs, refactor querying, update README (#11) [Teemu R]

  * Read from socket until no data available, disable double string encoding

  HS110 sends sometimes datagrams in chunks especially for get_daystat,
  this patch makes it to read until there is no more data to be read.

  As json.dumps() does JSON encoding already, there's no need to str()
  the year or month either.

  * Add cli.py, a simple script to query devices for debugging purposes.

  * allow easier importing with from pyHS100 import SmartPlug

  * move cli.py to examples, add short usage into README.md

  * Implement more available APIs, refactor querying code.

  This commit adds access to new properties, both read & write,  while keeping the old one (mostly) intact.
  Querying is refactored to be done inside _query_helper() method,
  which unwraps results automatically and rises SmartPlugException() in case of errors.
  Errors are to be handled by clients.

  New features:
  * Setting device alias (plug.alias = "name")
  * led read & write
  * icon read (doesn't seem to return anything without cloud support at least), write API is not known, throws an exception currently
  * time read (returns datetime), time write implemented, but not working even when no error is returned from the device
  * timezone read
  * mac read & write, writing is untested for now.

  Properties for easier access:
  * hw_info: return hw-specific elements from sysinfo
  * on_since: pretty-printed from sysinfo
  * location: latitude and longitued from sysinfo
  * rssi: rssi from sysinfo

  * Update README.md with examples of available features.

  * Handle comments from mweinelt

  * Refactor state handling, use booleans instead of strings

  * Fix issues raised during the review.

  Following issues are addressed by this commit:
  * All API is more or less commented (including return types, exceptions, ..)
  * Converted state to use
  * Added properties is_on, is_off for those who don't want to check against strings.
  * Handled most issues reported by pylint.
  * Adjusted _query_helper() to strip off err_code from the result object.
  * Fixed broken format() syntax for string formattings.

  * Fix ci woes plus one typo.

  * Do initialization after changing device properties, fix nits.

- Constants will be static members of SmartPlug. [Martin Weinelt]

- Set up hound-ci. [Martin Weinelt]

- Normalize docstrings, address flake8 & pylint recommendations. [Martin
  Weinelt]

- Properly detect advertised features, expose alias. [Martin Weinelt]

- Externalize the TP-Link Smart Home Protocol. [Martin Weinelt]

- HS200 support. [GadgetReactor]

  Update version to reflect latest changes

- Adding in support for the HS200 Wall switch referencing issues (#4),
  simplifying model determination. [Stephen Maggard]

- Adding in support for the HS200 Wall switch referencing issues (#4),
  simplifying model determination. [Stephen Maggard]

- Adding in support for the HS200 Wall switch referencing issues (#4)
  [Stephen Maggard]

- Refactors state property to use get_info() and removes hs100_status()
  [Georgi Kirichkov]

- Adds model check to current_consumption() and removes whitespace.
  [Georgi Kirichkov]

- Fixes indentation and removes extra whitespaces. [Georgi Kirichkov]

- Update setup.py. [GadgetReactor]

- Update LICENSE. [GadgetReactor]

  Updated to GPLv3 (instead of just copy and pasting)

0.2.0 (2016-10-17)
------------------

- Bumps the module version to 0.2.0. [Georgi Kirichkov]

- Adds additional comments, for better compliance with the Apache
  license. [Georgi Kirichkov]

- Makes the socket sending code compatible with both Python 2 and python
  3. [Georgi Kirichkov]

  Adds a shutdown to the socket used to send commands

- Refactors state() to use turn_on() and turn_off() [Georgi Kirichkov]

- Adds Energy Meter commands available on the TP-Link HS110. [Georgi
  Kirichkov]

  Also adds turn_on() and turn_off() commands to supplement the state

- Update pyHS100.py. [GadgetReactor]

- Update __init__.py. [GadgetReactor]

- Update __init__.py. [GadgetReactor]

0.1.2 (2016-07-09)
------------------

- 0.1.2. [GadgetReactor]

- Update setup.py. [GadgetReactor]

- Update setup.py. [GadgetReactor]

- Delete pyHS100.py. [GadgetReactor]

- Create pyHS100.py. [GadgetReactor]

- Create __init__.py. [GadgetReactor]

- Create setup.py. [GadgetReactor]

- Create pyHS100.py. [GadgetReactor]

- Initial commit. [GadgetReactor]


\* *This Changelog was automatically generated by [github_changelog_generator](https://github.com/github-changelog-generator/github-changelog-generator)*
