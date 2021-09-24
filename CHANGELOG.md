# Changelog

## [0.4.0.dev5](https://github.com/python-kasa/python-kasa/tree/0.4.0.dev5) (2021-09-24)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.4.0.dev4...0.4.0.dev5)

**Merged pull requests:**

- Add KL130 fixture, initial lightstrip tests [\#214](https://github.com/python-kasa/python-kasa/pull/214) ([rytilahti](https://github.com/rytilahti))
- Keep connection open and lock to prevent duplicate requests [\#213](https://github.com/python-kasa/python-kasa/pull/213) ([bdraco](https://github.com/bdraco))
- Cleanup discovery & add tests [\#212](https://github.com/python-kasa/python-kasa/pull/212) ([rytilahti](https://github.com/rytilahti))

## [0.4.0.dev4](https://github.com/python-kasa/python-kasa/tree/0.4.0.dev4) (2021-09-23)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.4.0.dev3...0.4.0.dev4)

**Implemented enhancements:**

- Improve emeterstatus API, move into own module [\#205](https://github.com/python-kasa/python-kasa/pull/205) ([rytilahti](https://github.com/rytilahti))
- Avoid temp array during encrypt and decrypt [\#204](https://github.com/python-kasa/python-kasa/pull/204) ([bdraco](https://github.com/bdraco))
- Add emeter support for strip sockets [\#203](https://github.com/python-kasa/python-kasa/pull/203) ([bdraco](https://github.com/bdraco))
- Add own device type for smartstrip children [\#201](https://github.com/python-kasa/python-kasa/pull/201) ([rytilahti](https://github.com/rytilahti))
- bulb: allow set\_hsv without v, add fallback ct range [\#200](https://github.com/python-kasa/python-kasa/pull/200) ([rytilahti](https://github.com/rytilahti))
- Improve bulb support \(alias, time settings\) [\#198](https://github.com/python-kasa/python-kasa/pull/198) ([rytilahti](https://github.com/rytilahti))
- Improve testing harness to allow tests on real devices [\#197](https://github.com/python-kasa/python-kasa/pull/197) ([rytilahti](https://github.com/rytilahti))
- cli: add human-friendly printout when calling temperature on non-supported devices [\#196](https://github.com/python-kasa/python-kasa/pull/196) ([JaydenRA](https://github.com/JaydenRA))

**Fixed bugs:**

- KL430: Throw error for Device specific information [\#189](https://github.com/python-kasa/python-kasa/issues/189)
- HS300 Children plugs have emeter [\#64](https://github.com/python-kasa/python-kasa/issues/64)
- dump\_devinfo: handle latitude/longitude keys properly [\#175](https://github.com/python-kasa/python-kasa/pull/175) ([rytilahti](https://github.com/rytilahti))

**Closed issues:**

- Feature Request - Toggle Command [\#188](https://github.com/python-kasa/python-kasa/issues/188)
- Is It Compatible With HS105? [\#186](https://github.com/python-kasa/python-kasa/issues/186)
- Cannot use some functions with KP303 [\#181](https://github.com/python-kasa/python-kasa/issues/181)
- Help needed - awaiting game  [\#179](https://github.com/python-kasa/python-kasa/issues/179)
- Version inconsistency between CLI and pip [\#177](https://github.com/python-kasa/python-kasa/issues/177)
- Release 0.4.0.dev3? [\#169](https://github.com/python-kasa/python-kasa/issues/169)
- Discover does not support specifying network interface [\#167](https://github.com/python-kasa/python-kasa/issues/167)
- Can't command or query HS200 v5 switch [\#161](https://github.com/python-kasa/python-kasa/issues/161)

**Merged pull requests:**

- Release 0.4.0.dev4 [\#210](https://github.com/python-kasa/python-kasa/pull/210) ([rytilahti](https://github.com/rytilahti))
- More CI fixes [\#208](https://github.com/python-kasa/python-kasa/pull/208) ([rytilahti](https://github.com/rytilahti))
- Fix CI dep installation [\#207](https://github.com/python-kasa/python-kasa/pull/207) ([rytilahti](https://github.com/rytilahti))
- Use github actions instead of azure pipelines [\#206](https://github.com/python-kasa/python-kasa/pull/206) ([rytilahti](https://github.com/rytilahti))
- Add KP115 fixture [\#202](https://github.com/python-kasa/python-kasa/pull/202) ([rytilahti](https://github.com/rytilahti))
- Perform initial update only using the sysinfo query [\#199](https://github.com/python-kasa/python-kasa/pull/199) ([rytilahti](https://github.com/rytilahti))
- Add real kasa KL430\(UN\) device dump [\#192](https://github.com/python-kasa/python-kasa/pull/192) ([iprodanovbg](https://github.com/iprodanovbg))
- Use less strict matcher for kl430 color temperature [\#190](https://github.com/python-kasa/python-kasa/pull/190) ([rytilahti](https://github.com/rytilahti))
- Add EP10\(US\) 1.0 1.0.2 fixture [\#174](https://github.com/python-kasa/python-kasa/pull/174) ([nbrew](https://github.com/nbrew))
- Add a note about using the discovery target parameter [\#168](https://github.com/python-kasa/python-kasa/pull/168) ([leandroreox](https://github.com/leandroreox))

## [0.4.0.dev3](https://github.com/python-kasa/python-kasa/tree/0.4.0.dev3) (2021-06-16)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.4.0.dev2...0.4.0.dev3)

**Fixed bugs:**

- `Unable to find a value for 'current'` error when attempting to query KL125 bulb emeter [\#142](https://github.com/python-kasa/python-kasa/issues/142)
- `Unknown color temperature range` error when attempting to query KL125 bulb state [\#141](https://github.com/python-kasa/python-kasa/issues/141)
- Simplify discovery query, refactor dump-devinfo [\#147](https://github.com/python-kasa/python-kasa/pull/147) ([rytilahti](https://github.com/rytilahti))
- Return None instead of raising an exception on missing, valid emeter keys [\#146](https://github.com/python-kasa/python-kasa/pull/146) ([rytilahti](https://github.com/rytilahti))

**Closed issues:**

- After installing, command `kasa` not found [\#165](https://github.com/python-kasa/python-kasa/issues/165)
- KL430 causing "non-hexadecimal number found in fromhex\(\) arg at position 2" error in smartdevice.py [\#159](https://github.com/python-kasa/python-kasa/issues/159)
- Cant get smart strip children to work [\#144](https://github.com/python-kasa/python-kasa/issues/144)
- `kasa --host 192.168.1.67 wifi join <ssid>` does not change network [\#139](https://github.com/python-kasa/python-kasa/issues/139)
- Poetry returns error when installing dependencies [\#131](https://github.com/python-kasa/python-kasa/issues/131)
- 'kasa wifi scan' raises RuntimeError [\#127](https://github.com/python-kasa/python-kasa/issues/127)
- Runtime Error when I execute Kasa emeter command [\#124](https://github.com/python-kasa/python-kasa/issues/124)
- Add ability to control individual sockets on KP400 [\#121](https://github.com/python-kasa/python-kasa/issues/121)
- HS105\(US\) HW 5.0/SW 1.0.2 Not Working [\#119](https://github.com/python-kasa/python-kasa/issues/119)
- HS110\(UK\) not discoverable [\#113](https://github.com/python-kasa/python-kasa/issues/113)
- Stopping Kasa SmartDevices from phoning home [\#111](https://github.com/python-kasa/python-kasa/issues/111)
- TP Link Dimmer switch \(HS220\) hardware version 2.0 not being discovered [\#105](https://github.com/python-kasa/python-kasa/issues/105)
- Support for P100 Smart Plug [\#83](https://github.com/python-kasa/python-kasa/issues/83)

**Merged pull requests:**

- Prepare 0.4.0.dev3 [\#172](https://github.com/python-kasa/python-kasa/pull/172) ([rytilahti](https://github.com/rytilahti))
- Simplify mac address handling [\#162](https://github.com/python-kasa/python-kasa/pull/162) ([rytilahti](https://github.com/rytilahti))
- Added KL125 and HS200 fixture dumps and updated tests to run on new format [\#160](https://github.com/python-kasa/python-kasa/pull/160) ([brianthedavis](https://github.com/brianthedavis))
- Add KL125 bulb definition [\#143](https://github.com/python-kasa/python-kasa/pull/143) ([mdarnol](https://github.com/mdarnol))
- README.md: Add link to MQTT interface for python-kasa [\#140](https://github.com/python-kasa/python-kasa/pull/140) ([flavio-fernandes](https://github.com/flavio-fernandes))
- Fix documentation on Smart strips [\#136](https://github.com/python-kasa/python-kasa/pull/136) ([flavio-fernandes](https://github.com/flavio-fernandes))
- add tapo link, fix tplink-smarthome-simulator link [\#133](https://github.com/python-kasa/python-kasa/pull/133) ([rytilahti](https://github.com/rytilahti))
- Leverage data from UDP discovery to initialize device structure [\#132](https://github.com/python-kasa/python-kasa/pull/132) ([dlee1j1](https://github.com/dlee1j1))
- Improve cli documentation for bulbs and power strips [\#123](https://github.com/python-kasa/python-kasa/pull/123) ([rytilahti](https://github.com/rytilahti))
- Add HS220 hw 2.0 fixture [\#107](https://github.com/python-kasa/python-kasa/pull/107) ([appleguru](https://github.com/appleguru))

## [0.4.0.dev2](https://github.com/python-kasa/python-kasa/tree/0.4.0.dev2) (2020-11-21)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.4.0.dev1...0.4.0.dev2)

**Implemented enhancements:**

- 'Interface' parameter added to discovery process [\#79](https://github.com/python-kasa/python-kasa/pull/79) ([dmitryelj](https://github.com/dmitryelj))

**Fixed bugs:**

- Simplify device class detection for discovery, fix hardcoded timeout [\#112](https://github.com/python-kasa/python-kasa/pull/112) ([rytilahti](https://github.com/rytilahti))
- Update cli.py to addresss crash on year/month calls and improve output formatting [\#103](https://github.com/python-kasa/python-kasa/pull/103) ([BuongiornoTexas](https://github.com/BuongiornoTexas))

**Closed issues:**

- TPLINK HS100 firmware 4.1 no longer has TCP 9999 available [\#114](https://github.com/python-kasa/python-kasa/issues/114)
- 7.1.2 Update to asyncclick breaks github install of python-kasa [\#106](https://github.com/python-kasa/python-kasa/issues/106)
- cli emeter year and month functions fail [\#102](https://github.com/python-kasa/python-kasa/issues/102)
- how to know the duration for which the plug was ON? [\#99](https://github.com/python-kasa/python-kasa/issues/99)
- problem controlling the smartplug through a controller [\#98](https://github.com/python-kasa/python-kasa/issues/98)
- unable to install [\#97](https://github.com/python-kasa/python-kasa/issues/97)
- Install on Ubuntu 18.04 no luck [\#96](https://github.com/python-kasa/python-kasa/issues/96)
- issue with installation [\#95](https://github.com/python-kasa/python-kasa/issues/95)
- Running via Crontab [\#92](https://github.com/python-kasa/python-kasa/issues/92)
- Issues with setup [\#91](https://github.com/python-kasa/python-kasa/issues/91)

**Merged pull requests:**

- Release 0.4.0.dev2 [\#118](https://github.com/python-kasa/python-kasa/pull/118) ([rytilahti](https://github.com/rytilahti))
- Pin dependencies on major versions, add poetry.lock [\#94](https://github.com/python-kasa/python-kasa/pull/94) ([rytilahti](https://github.com/rytilahti))

## [0.4.0.dev1](https://github.com/python-kasa/python-kasa/tree/0.4.0.dev1) (2020-07-28)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.4.0.dev0...0.4.0.dev1)

**Implemented enhancements:**

- KL430 support [\#67](https://github.com/python-kasa/python-kasa/issues/67)
- Improve retry logic for discovery, messaging \(was: Handle empty responses\) [\#38](https://github.com/python-kasa/python-kasa/issues/38)
- Add support for lightstrips \(KL430\) [\#74](https://github.com/python-kasa/python-kasa/pull/74) ([rytilahti](https://github.com/rytilahti))

**Closed issues:**

- I don't python... how do I make this executable? [\#88](https://github.com/python-kasa/python-kasa/issues/88)
- ImportError: cannot import name 'smartplug' [\#87](https://github.com/python-kasa/python-kasa/issues/87)
- not able to pip install the library [\#82](https://github.com/python-kasa/python-kasa/issues/82)
- Discover.discover\(\) add selecting network interface \[pull request\] [\#78](https://github.com/python-kasa/python-kasa/issues/78)
- LB100 unable to turn on or off the lights [\#68](https://github.com/python-kasa/python-kasa/issues/68)
- Improve poetry usage documentation [\#60](https://github.com/python-kasa/python-kasa/issues/60)
- sys\_info not None fails assertion [\#55](https://github.com/python-kasa/python-kasa/issues/55)
- Upload pre-release to pypi for easier testing [\#17](https://github.com/python-kasa/python-kasa/issues/17)

**Merged pull requests:**

- Release 0.4.0.dev1 [\#93](https://github.com/python-kasa/python-kasa/pull/93) ([rytilahti](https://github.com/rytilahti))
- add a small example script to show library usage [\#90](https://github.com/python-kasa/python-kasa/pull/90) ([rytilahti](https://github.com/rytilahti))
- add .readthedocs.yml required for poetry builds [\#89](https://github.com/python-kasa/python-kasa/pull/89) ([rytilahti](https://github.com/rytilahti))
- Improve installation instructions [\#86](https://github.com/python-kasa/python-kasa/pull/86) ([rytilahti](https://github.com/rytilahti))
- cli: Fix incorrect use of asyncio.run for temperature command [\#85](https://github.com/python-kasa/python-kasa/pull/85) ([rytilahti](https://github.com/rytilahti))
- Add parse\_pcap to devtools, improve readme on contributing [\#84](https://github.com/python-kasa/python-kasa/pull/84) ([rytilahti](https://github.com/rytilahti))
- Add --transition to bulb-specific cli commands, fix turn\_{on,off} signatures [\#81](https://github.com/python-kasa/python-kasa/pull/81) ([rytilahti](https://github.com/rytilahti))
- Improve bulb API, force turn on for all light changes as offline changes are not supported [\#76](https://github.com/python-kasa/python-kasa/pull/76) ([rytilahti](https://github.com/rytilahti))
- Simplify API documentation by using doctests [\#73](https://github.com/python-kasa/python-kasa/pull/73) ([rytilahti](https://github.com/rytilahti))
- Bulbs: allow specifying transition for state changes [\#70](https://github.com/python-kasa/python-kasa/pull/70) ([rytilahti](https://github.com/rytilahti))
- Add transition support for SmartDimmer [\#69](https://github.com/python-kasa/python-kasa/pull/69) ([connorproctor](https://github.com/connorproctor))

## [0.4.0.dev0](https://github.com/python-kasa/python-kasa/tree/0.4.0.dev0) (2020-05-27)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.3.5...0.4.0.dev0)

**Implemented enhancements:**

- Add commands to control the wifi settings [\#45](https://github.com/python-kasa/python-kasa/pull/45) ([rytilahti](https://github.com/rytilahti))

**Fixed bugs:**

- HSV cli command not working [\#43](https://github.com/python-kasa/python-kasa/issues/43)

**Closed issues:**

- Pull request \#54 broke installer? [\#66](https://github.com/python-kasa/python-kasa/issues/66)
- RFC: remove implicit updates after state changes? [\#61](https://github.com/python-kasa/python-kasa/issues/61)
- How to install? [\#57](https://github.com/python-kasa/python-kasa/issues/57)
- Request all necessary information during update\(\) [\#53](https://github.com/python-kasa/python-kasa/issues/53)
- HS107 Support [\#37](https://github.com/python-kasa/python-kasa/issues/37)
- Separate dimmer-related code from smartplug class [\#33](https://github.com/python-kasa/python-kasa/issues/33)
- Add Mac OSX and Windows for CI [\#30](https://github.com/python-kasa/python-kasa/issues/30)
- KP303\(UK\) does not pass check with pytest [\#27](https://github.com/python-kasa/python-kasa/issues/27)
- Remove sync interface wrapper [\#12](https://github.com/python-kasa/python-kasa/issues/12)
- Mass close pyhs100 issues and PRs [\#11](https://github.com/python-kasa/python-kasa/issues/11)
- Update readme [\#10](https://github.com/python-kasa/python-kasa/issues/10)
- Add contribution guidelines and instructions [\#8](https://github.com/python-kasa/python-kasa/issues/8)
- Convert discovery to use asyncio [\#7](https://github.com/python-kasa/python-kasa/issues/7)
- Python Version? [\#4](https://github.com/python-kasa/python-kasa/issues/4)
- Fix failing tests: KeyError: 'relay\_state' [\#2](https://github.com/python-kasa/python-kasa/issues/2)

**Merged pull requests:**

- Add retries to protocol queries [\#65](https://github.com/python-kasa/python-kasa/pull/65) ([rytilahti](https://github.com/rytilahti))
- General cleanups all around \(janitoring\) [\#63](https://github.com/python-kasa/python-kasa/pull/63) ([rytilahti](https://github.com/rytilahti))
- Improve dimmer support [\#62](https://github.com/python-kasa/python-kasa/pull/62) ([rytilahti](https://github.com/rytilahti))
- Optimize I/O access [\#59](https://github.com/python-kasa/python-kasa/pull/59) ([rytilahti](https://github.com/rytilahti))
- Remove unnecessary f-string definition to make tests pass [\#58](https://github.com/python-kasa/python-kasa/pull/58) ([rytilahti](https://github.com/rytilahti))
- Convert to use poetry & pyproject.toml for dep & build management [\#54](https://github.com/python-kasa/python-kasa/pull/54) ([rytilahti](https://github.com/rytilahti))
- Add fixture for KL60 [\#52](https://github.com/python-kasa/python-kasa/pull/52) ([rytilahti](https://github.com/rytilahti))
- Ignore D202 where necessary [\#50](https://github.com/python-kasa/python-kasa/pull/50) ([rytilahti](https://github.com/rytilahti))
- Support wifi scan & join for bulbs using a different interface [\#49](https://github.com/python-kasa/python-kasa/pull/49) ([rytilahti](https://github.com/rytilahti))
- Return on\_since only when its available and the device is on [\#48](https://github.com/python-kasa/python-kasa/pull/48) ([rytilahti](https://github.com/rytilahti))
- Allow 0 brightness for smartdimmer [\#47](https://github.com/python-kasa/python-kasa/pull/47) ([rytilahti](https://github.com/rytilahti))
- async++, small powerstrip improvements [\#46](https://github.com/python-kasa/python-kasa/pull/46) ([rytilahti](https://github.com/rytilahti))
- Check for emeter support on power strips/multiple plug outlets [\#41](https://github.com/python-kasa/python-kasa/pull/41) ([acmay](https://github.com/acmay))
- Remove unnecessary cache [\#40](https://github.com/python-kasa/python-kasa/pull/40) ([rytilahti](https://github.com/rytilahti))
- Add in some new device types [\#39](https://github.com/python-kasa/python-kasa/pull/39) ([acmay](https://github.com/acmay))
- Add test fixture for KL130 [\#35](https://github.com/python-kasa/python-kasa/pull/35) ([bdraco](https://github.com/bdraco))
- Move dimmer support to its own class [\#34](https://github.com/python-kasa/python-kasa/pull/34) ([rytilahti](https://github.com/rytilahti))
- Fix azure pipeline badge [\#32](https://github.com/python-kasa/python-kasa/pull/32) ([rytilahti](https://github.com/rytilahti))
- Enable Windows & OSX builds [\#31](https://github.com/python-kasa/python-kasa/pull/31) ([rytilahti](https://github.com/rytilahti))
- Depend on py3.7+ for tox, add python 3.8 to azure pipeline targets [\#29](https://github.com/python-kasa/python-kasa/pull/29) ([rytilahti](https://github.com/rytilahti))
- Add KP303 to the list of powerstrips [\#28](https://github.com/python-kasa/python-kasa/pull/28) ([rytilahti](https://github.com/rytilahti))
- Move child socket handling to its own SmartStripPlug class [\#26](https://github.com/python-kasa/python-kasa/pull/26) ([rytilahti](https://github.com/rytilahti))
- Adding KP303 to supported devices [\#25](https://github.com/python-kasa/python-kasa/pull/25) ([epicalex](https://github.com/epicalex))
- use pytestmark to avoid repeating asyncio mark [\#24](https://github.com/python-kasa/python-kasa/pull/24) ([rytilahti](https://github.com/rytilahti))
- Cleanup constructors by removing ioloop and protocol arguments [\#23](https://github.com/python-kasa/python-kasa/pull/23) ([rytilahti](https://github.com/rytilahti))
- Add \(some\) tests to the cli tool [\#22](https://github.com/python-kasa/python-kasa/pull/22) ([rytilahti](https://github.com/rytilahti))
- Test against the newly added device fixtures  [\#21](https://github.com/python-kasa/python-kasa/pull/21) ([rytilahti](https://github.com/rytilahti))
- move testing reqs to requirements\_test.txt, add pytest-asyncio for pipelines [\#20](https://github.com/python-kasa/python-kasa/pull/20) ([rytilahti](https://github.com/rytilahti))
- Remove unused save option and add scrubbing [\#19](https://github.com/python-kasa/python-kasa/pull/19) ([TheGardenMonkey](https://github.com/TheGardenMonkey))
- Add real kasa device dumps [\#18](https://github.com/python-kasa/python-kasa/pull/18) ([TheGardenMonkey](https://github.com/TheGardenMonkey))
- Fix dump-discover to use asyncio.run [\#16](https://github.com/python-kasa/python-kasa/pull/16) ([rytilahti](https://github.com/rytilahti))
- Add device\_id property, rename context to child\_id [\#15](https://github.com/python-kasa/python-kasa/pull/15) ([rytilahti](https://github.com/rytilahti))
- Remove sync interface, add asyncio discovery [\#14](https://github.com/python-kasa/python-kasa/pull/14) ([rytilahti](https://github.com/rytilahti))
- Remove --ip which was just an alias to --host [\#6](https://github.com/python-kasa/python-kasa/pull/6) ([rytilahti](https://github.com/rytilahti))
- Set minimum requirement to python 3.7 [\#5](https://github.com/python-kasa/python-kasa/pull/5) ([rytilahti](https://github.com/rytilahti))
- change ID of Azure Pipeline [\#3](https://github.com/python-kasa/python-kasa/pull/3) ([basnijholt](https://github.com/basnijholt))
- Mass rename to \(python-\)kasa [\#1](https://github.com/python-kasa/python-kasa/pull/1) ([rytilahti](https://github.com/rytilahti))

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
