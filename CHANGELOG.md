# Changelog

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
- Make timeout adjustable [\#494](https://github.com/python-kasa/python-kasa/pull/494) (@bdraco)
- Add support for alternative discovery protocol \(20002/udp\) [\#488](https://github.com/python-kasa/python-kasa/pull/488) (@sdb9696)
- Add discovery timeout parameter [\#486](https://github.com/python-kasa/python-kasa/pull/486) (@sdb9696)
- Add devtools script to create module fixtures [\#404](https://github.com/python-kasa/python-kasa/pull/404) (@rytilahti)

**Fixed bugs:**

- Fix on\_since for smartstrip sockets [\#529](https://github.com/python-kasa/python-kasa/pull/529) (@rytilahti)
- Fix every other query tries to fetch known unsupported features [\#520](https://github.com/python-kasa/python-kasa/pull/520) (@bdraco)

**Documentation updates:**

- Mark KS2{20}M as partially supported [\#508](https://github.com/python-kasa/python-kasa/pull/508) (@lschweiss)
- Document cli tool --target for discovery [\#497](https://github.com/python-kasa/python-kasa/pull/497) (@rytilahti)

**Closed issues:**

- Error running kasa command on the Raspberry PI [\#525](https://github.com/python-kasa/python-kasa/issues/525)
- Installation Problems \(Python Version?\) [\#523](https://github.com/python-kasa/python-kasa/issues/523)
- What are the units in the emeter readings? [\#514](https://github.com/python-kasa/python-kasa/issues/514)
- Set Alias via Command Line [\#511](https://github.com/python-kasa/python-kasa/issues/511)
- How do I know if my device supports emeter? [\#510](https://github.com/python-kasa/python-kasa/issues/510)
- Getting Invalid KeyError when getting sysinfo on an EP40 device [\#500](https://github.com/python-kasa/python-kasa/issues/500)
- Running kasa discover on subnet broadcasts only [\#496](https://github.com/python-kasa/python-kasa/issues/496)
- Failed to discover kasa switchs on the network [\#495](https://github.com/python-kasa/python-kasa/issues/495)
- \[Feature Request\] Add a toggle command [\#492](https://github.com/python-kasa/python-kasa/issues/492)
- \[Feature Request\] Pydantic 2.0+ Support [\#491](https://github.com/python-kasa/python-kasa/issues/491)
- Support for EP10 Plug [\#170](https://github.com/python-kasa/python-kasa/issues/170)

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

- Release 0.5.3 [\#485](https://github.com/python-kasa/python-kasa/pull/485) (@rytilahti)
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

**Closed issues:**

- Powershell version? [\#461](https://github.com/python-kasa/python-kasa/issues/461)
- Add `set_cold_time` to Motion module [\#452](https://github.com/python-kasa/python-kasa/issues/452)
- Discover.discover\(\) only returning ip adress on ep10 outlet [\#447](https://github.com/python-kasa/python-kasa/issues/447)
- Query current wifi config? [\#445](https://github.com/python-kasa/python-kasa/issues/445)
- bulb.turn\_off making device undiscoverable [\#444](https://github.com/python-kasa/python-kasa/issues/444)
- best privacy practices for Kasa devices [\#438](https://github.com/python-kasa/python-kasa/issues/438)
- Access device from different network [\#424](https://github.com/python-kasa/python-kasa/issues/424)
- Lots of test failure with 0.5.0 [\#411](https://github.com/python-kasa/python-kasa/issues/411)

**Merged pull requests:**

- Release 0.5.2 [\#475](https://github.com/python-kasa/python-kasa/pull/475) (@rytilahti)
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

- detecting when a switch changes state [\#427](https://github.com/python-kasa/python-kasa/issues/427)
- discovery fails for aliases [\#426](https://github.com/python-kasa/python-kasa/issues/426)
- traceback when no devices exist [\#425](https://github.com/python-kasa/python-kasa/issues/425)
- Discover.discover\(\) in a cron that runs every 1 min [\#421](https://github.com/python-kasa/python-kasa/issues/421)
- add Schedule rule? [\#418](https://github.com/python-kasa/python-kasa/issues/418)
- Cannot find EP10 using kasa discover [\#417](https://github.com/python-kasa/python-kasa/issues/417)
- modulenotfound error [\#414](https://github.com/python-kasa/python-kasa/issues/414)
- Issue enabling motion sensor, ES20M\(US\) [\#408](https://github.com/python-kasa/python-kasa/issues/408)
- HS103 not discovered by kasa CLI [\#406](https://github.com/python-kasa/python-kasa/issues/406)
- Multiple warnings from running pytest due to asyncio issues [\#396](https://github.com/python-kasa/python-kasa/issues/396)
- Transition ignored with KL420L5 light strips [\#389](https://github.com/python-kasa/python-kasa/issues/389)
- cli.py passes a dictionary \(TYPE\_TO\_CLASS\) to click.Choice which takes a Sequence\[str\]  [\#384](https://github.com/python-kasa/python-kasa/issues/384)
- Error running `kasa wifi scan` [\#376](https://github.com/python-kasa/python-kasa/issues/376)
- Unable to connect to brand new EP40 v1.8 [\#366](https://github.com/python-kasa/python-kasa/issues/366)
- Add support for setting default behaviors for a soft or hard power on of the bulb [\#365](https://github.com/python-kasa/python-kasa/issues/365)
- Set bulb hue using variable [\#361](https://github.com/python-kasa/python-kasa/issues/361)
- Help with SmartLightStrip set\_custom\_effect [\#360](https://github.com/python-kasa/python-kasa/issues/360)
- Import "kasa" could not be resolved [\#357](https://github.com/python-kasa/python-kasa/issues/357)
- Wall switch ES20M \(--type dimmer\) is working [\#353](https://github.com/python-kasa/python-kasa/issues/353)
- HS107 reports `state` not `relay_state` throwing a `KeyError` [\#349](https://github.com/python-kasa/python-kasa/issues/349)
- Error Installing On Windows 10 [\#347](https://github.com/python-kasa/python-kasa/issues/347)
- Error using Kasa [\#346](https://github.com/python-kasa/python-kasa/issues/346)
- KS220M\(US\) support [\#268](https://github.com/python-kasa/python-kasa/issues/268)
- Add machine-readable output [\#209](https://github.com/python-kasa/python-kasa/issues/209)
- Can we donate? [\#77](https://github.com/python-kasa/python-kasa/issues/77)

**Merged pull requests:**

- Prepare 0.5.1 [\#434](https://github.com/python-kasa/python-kasa/pull/434) (@rytilahti)
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

**Closed issues:**

- "on since" changes [\#295](https://github.com/python-kasa/python-kasa/issues/295)
- How to access KP115 runtime data? [\#244](https://github.com/python-kasa/python-kasa/issues/244)
- How to resolve "Detected protocol reuse between different event loop" warning? [\#238](https://github.com/python-kasa/python-kasa/issues/238)
- Handle discovery where multiple LAN interfaces exist [\#104](https://github.com/python-kasa/python-kasa/issues/104)
- Hyper-V \(and probably virtualbox\) break UDP discovery [\#101](https://github.com/python-kasa/python-kasa/issues/101)
- Trying to get extended lightstrip functionality [\#100](https://github.com/python-kasa/python-kasa/issues/100)
- Can the HS105 be controlled without internet? [\#72](https://github.com/python-kasa/python-kasa/issues/72)

**Merged pull requests:**

- Prepare 0.5.0 [\#342](https://github.com/python-kasa/python-kasa/pull/342) (@rytilahti)
- Add fixtures for kl420 [\#339](https://github.com/python-kasa/python-kasa/pull/339) (@bdraco)

## [0.4.3](https://github.com/python-kasa/python-kasa/tree/0.4.3) (2022-04-05)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.4.2...0.4.3)

**Fixed bugs:**

- Divide by zero when HS300 powerstrip is discovered [\#292](https://github.com/python-kasa/python-kasa/issues/292)
- Ensure bulb state is restored when turning back on [\#330](https://github.com/python-kasa/python-kasa/pull/330) (@bdraco)

**Closed issues:**

- KL420L5 controls [\#327](https://github.com/python-kasa/python-kasa/issues/327)

**Merged pull requests:**

- Release 0.4.3 [\#332](https://github.com/python-kasa/python-kasa/pull/332) (@rytilahti)
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

**Closed issues:**

- SmartDeviceException: Communication error on system:set\_relay\_state [\#309](https://github.com/python-kasa/python-kasa/issues/309)
- Add Support: ES20M and KS200M motion/light switches [\#308](https://github.com/python-kasa/python-kasa/issues/308)
- New problem with installing on Ubuntu 20.04.3 LTS [\#305](https://github.com/python-kasa/python-kasa/issues/305)
- KeyError: 'emeter' when discovering [\#302](https://github.com/python-kasa/python-kasa/issues/302)
- RuntimeError: Event loop is closed  [\#291](https://github.com/python-kasa/python-kasa/issues/291)
- provisioning format [\#290](https://github.com/python-kasa/python-kasa/issues/290)
- Fix CI publishing on pypi [\#222](https://github.com/python-kasa/python-kasa/issues/222)
- LED strips effects are not supported \(was LEDs is not turning on after switching on\) [\#191](https://github.com/python-kasa/python-kasa/issues/191)

**Merged pull requests:**

- Release 0.4.2 [\#321](https://github.com/python-kasa/python-kasa/pull/321) (@rytilahti)
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

**Closed issues:**

- Control device with alias via python api? [\#285](https://github.com/python-kasa/python-kasa/issues/285)
- Can't install using pip install python-kasa [\#255](https://github.com/python-kasa/python-kasa/issues/255)
- Kasa Smart Bulb KL135 - Unknown color temperature range error [\#252](https://github.com/python-kasa/python-kasa/issues/252)
- KL400 Support [\#247](https://github.com/python-kasa/python-kasa/issues/247)
- Cloud support? [\#245](https://github.com/python-kasa/python-kasa/issues/245)
- Support for kp401 [\#241](https://github.com/python-kasa/python-kasa/issues/241)
- LB130 Bulb stopped working [\#237](https://github.com/python-kasa/python-kasa/issues/237)
- Unable to constantly query bulb in loop [\#225](https://github.com/python-kasa/python-kasa/issues/225)
- HS103: Unable to query the device: unpack requires a buffer of 4 bytes [\#187](https://github.com/python-kasa/python-kasa/issues/187)
- Help request - query value [\#171](https://github.com/python-kasa/python-kasa/issues/171)
- Can't Discover Devices [\#164](https://github.com/python-kasa/python-kasa/issues/164)
- Concurrency performance question [\#110](https://github.com/python-kasa/python-kasa/issues/110)
- Define the port by self? [\#108](https://github.com/python-kasa/python-kasa/issues/108)
- Convert homeassistant integration to use the library [\#9](https://github.com/python-kasa/python-kasa/issues/9)

**Merged pull requests:**

- Prepare 0.4.1 [\#288](https://github.com/python-kasa/python-kasa/pull/288) (@rytilahti)
- Publish to pypi on github release published [\#287](https://github.com/python-kasa/python-kasa/pull/287) (@rytilahti)
- Relax asyncclick version requirement [\#286](https://github.com/python-kasa/python-kasa/pull/286) (@rytilahti)
- Do not crash on discovery on WSL [\#283](https://github.com/python-kasa/python-kasa/pull/283) (@rytilahti)
- Add python 3.10 to CI [\#279](https://github.com/python-kasa/python-kasa/pull/279) (@rytilahti)
- Use codecov-action@v2 for CI [\#277](https://github.com/python-kasa/python-kasa/pull/277) (@rytilahti)
- Add coverage\[toml\] dependency to fix coverage on CI [\#271](https://github.com/python-kasa/python-kasa/pull/271) (@rytilahti)
- Allow publish on test pypi workflow to fail [\#248](https://github.com/python-kasa/python-kasa/pull/248) (@rytilahti)

## [0.4.0](https://github.com/python-kasa/python-kasa/tree/0.4.0) (2021-09-27)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.4.0.dev5...0.4.0)

**Implemented enhancements:**

- Fix lock being unexpectedly reset on close [\#218](https://github.com/python-kasa/python-kasa/pull/218) (@bdraco)
- Avoid calling pformat unless debug logging is enabled [\#217](https://github.com/python-kasa/python-kasa/pull/217) (@bdraco)

**Closed issues:**

- Debug logging in protocol.py is the majority of the execution time [\#216](https://github.com/python-kasa/python-kasa/issues/216)

**Merged pull requests:**

- Release 0.4.0 [\#221](https://github.com/python-kasa/python-kasa/pull/221) (@rytilahti)
- Add github workflow for pypi publishing [\#220](https://github.com/python-kasa/python-kasa/pull/220) (@rytilahti)
- Add host information to protocol debug logs [\#219](https://github.com/python-kasa/python-kasa/pull/219) (@rytilahti)

## [0.4.0.dev5](https://github.com/python-kasa/python-kasa/tree/0.4.0.dev5) (2021-09-24)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.4.0.dev4...0.4.0.dev5)

**Implemented enhancements:**

- Keep connection open and lock to prevent duplicate requests [\#213](https://github.com/python-kasa/python-kasa/pull/213) (@bdraco)

**Merged pull requests:**

- Release 0.4.0.dev5 [\#215](https://github.com/python-kasa/python-kasa/pull/215) (@rytilahti)
- Add KL130 fixture, initial lightstrip tests [\#214](https://github.com/python-kasa/python-kasa/pull/214) (@rytilahti)
- Cleanup discovery & add tests [\#212](https://github.com/python-kasa/python-kasa/pull/212) (@rytilahti)

## [0.4.0.dev4](https://github.com/python-kasa/python-kasa/tree/0.4.0.dev4) (2021-09-23)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.4.0.dev3...0.4.0.dev4)

**Implemented enhancements:**

- Improve emeterstatus API, move into own module [\#205](https://github.com/python-kasa/python-kasa/pull/205) (@rytilahti)
- Avoid temp array during encrypt and decrypt [\#204](https://github.com/python-kasa/python-kasa/pull/204) (@bdraco)
- Add emeter support for strip sockets [\#203](https://github.com/python-kasa/python-kasa/pull/203) (@bdraco)
- Add own device type for smartstrip children [\#201](https://github.com/python-kasa/python-kasa/pull/201) (@rytilahti)
- bulb: allow set\_hsv without v, add fallback ct range [\#200](https://github.com/python-kasa/python-kasa/pull/200) (@rytilahti)
- Improve bulb support \(alias, time settings\) [\#198](https://github.com/python-kasa/python-kasa/pull/198) (@rytilahti)
- Improve testing harness to allow tests on real devices [\#197](https://github.com/python-kasa/python-kasa/pull/197) (@rytilahti)
- cli: add human-friendly printout when calling temperature on non-supported devices [\#196](https://github.com/python-kasa/python-kasa/pull/196) (@JaydenRA)

**Fixed bugs:**

- KL430: Throw error for Device specific information [\#189](https://github.com/python-kasa/python-kasa/issues/189)
- HS300 Children plugs have emeter [\#64](https://github.com/python-kasa/python-kasa/issues/64)
- dump\_devinfo: handle latitude/longitude keys properly [\#175](https://github.com/python-kasa/python-kasa/pull/175) (@rytilahti)

**Documentation updates:**

- Discover does not support specifying network interface [\#167](https://github.com/python-kasa/python-kasa/issues/167)

**Closed issues:**

- Feature Request - Toggle Command [\#188](https://github.com/python-kasa/python-kasa/issues/188)
- Is It Compatible With HS105? [\#186](https://github.com/python-kasa/python-kasa/issues/186)
- Cannot use some functions with KP303 [\#181](https://github.com/python-kasa/python-kasa/issues/181)
- Help needed - awaiting game  [\#179](https://github.com/python-kasa/python-kasa/issues/179)
- Version inconsistency between CLI and pip [\#177](https://github.com/python-kasa/python-kasa/issues/177)
- Release 0.4.0.dev3? [\#169](https://github.com/python-kasa/python-kasa/issues/169)
- Can't command or query HS200 v5 switch [\#161](https://github.com/python-kasa/python-kasa/issues/161)

**Merged pull requests:**

- Release 0.4.0.dev4 [\#210](https://github.com/python-kasa/python-kasa/pull/210) (@rytilahti)
- More CI fixes [\#208](https://github.com/python-kasa/python-kasa/pull/208) (@rytilahti)
- Fix CI dep installation [\#207](https://github.com/python-kasa/python-kasa/pull/207) (@rytilahti)
- Use github actions instead of azure pipelines [\#206](https://github.com/python-kasa/python-kasa/pull/206) (@rytilahti)
- Add KP115 fixture [\#202](https://github.com/python-kasa/python-kasa/pull/202) (@rytilahti)
- Perform initial update only using the sysinfo query [\#199](https://github.com/python-kasa/python-kasa/pull/199) (@rytilahti)
- Add real kasa KL430\(UN\) device dump [\#192](https://github.com/python-kasa/python-kasa/pull/192) (@iprodanovbg)
- Use less strict matcher for kl430 color temperature [\#190](https://github.com/python-kasa/python-kasa/pull/190) (@rytilahti)
- Add EP10\(US\) 1.0 1.0.2 fixture [\#174](https://github.com/python-kasa/python-kasa/pull/174) (@nbrew)
- Add a note about using the discovery target parameter [\#168](https://github.com/python-kasa/python-kasa/pull/168) (@leandroreox)

## [0.4.0.dev3](https://github.com/python-kasa/python-kasa/tree/0.4.0.dev3) (2021-06-16)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.4.0.dev2...0.4.0.dev3)

**Fixed bugs:**

- `Unable to find a value for 'current'` error when attempting to query KL125 bulb emeter [\#142](https://github.com/python-kasa/python-kasa/issues/142)
- `Unknown color temperature range` error when attempting to query KL125 bulb state [\#141](https://github.com/python-kasa/python-kasa/issues/141)
- Simplify discovery query, refactor dump-devinfo [\#147](https://github.com/python-kasa/python-kasa/pull/147) (@rytilahti)
- Return None instead of raising an exception on missing, valid emeter keys [\#146](https://github.com/python-kasa/python-kasa/pull/146) (@rytilahti)

**Documentation updates:**

- Add ability to control individual sockets on KP400 [\#121](https://github.com/python-kasa/python-kasa/issues/121)
- Improve cli documentation for bulbs and power strips [\#123](https://github.com/python-kasa/python-kasa/pull/123) (@rytilahti)

**Closed issues:**

- After installing, command `kasa` not found [\#165](https://github.com/python-kasa/python-kasa/issues/165)
- KL430 causing "non-hexadecimal number found in fromhex\(\) arg at position 2" error in smartdevice.py [\#159](https://github.com/python-kasa/python-kasa/issues/159)
- Cant get smart strip children to work [\#144](https://github.com/python-kasa/python-kasa/issues/144)
- `kasa --host 192.168.1.67 wifi join <ssid>` does not change network [\#139](https://github.com/python-kasa/python-kasa/issues/139)
- Poetry returns error when installing dependencies [\#131](https://github.com/python-kasa/python-kasa/issues/131)
- 'kasa wifi scan' raises RuntimeError [\#127](https://github.com/python-kasa/python-kasa/issues/127)
- Runtime Error when I execute Kasa emeter command [\#124](https://github.com/python-kasa/python-kasa/issues/124)
- HS105\(US\) HW 5.0/SW 1.0.2 Not Working [\#119](https://github.com/python-kasa/python-kasa/issues/119)
- HS110\(UK\) not discoverable [\#113](https://github.com/python-kasa/python-kasa/issues/113)
- Stopping Kasa SmartDevices from phoning home [\#111](https://github.com/python-kasa/python-kasa/issues/111)
- TP Link Dimmer switch \(HS220\) hardware version 2.0 not being discovered [\#105](https://github.com/python-kasa/python-kasa/issues/105)
- Support for P100 Smart Plug [\#83](https://github.com/python-kasa/python-kasa/issues/83)

**Merged pull requests:**

- Prepare 0.4.0.dev3 [\#172](https://github.com/python-kasa/python-kasa/pull/172) (@rytilahti)
- Simplify mac address handling [\#162](https://github.com/python-kasa/python-kasa/pull/162) (@rytilahti)
- Added KL125 and HS200 fixture dumps and updated tests to run on new format [\#160](https://github.com/python-kasa/python-kasa/pull/160) (@brianthedavis)
- Add KL125 bulb definition [\#143](https://github.com/python-kasa/python-kasa/pull/143) (@mdarnol)
- README.md: Add link to MQTT interface for python-kasa [\#140](https://github.com/python-kasa/python-kasa/pull/140) (@flavio-fernandes)
- Fix documentation on Smart strips [\#136](https://github.com/python-kasa/python-kasa/pull/136) (@flavio-fernandes)
- add tapo link, fix tplink-smarthome-simulator link [\#133](https://github.com/python-kasa/python-kasa/pull/133) (@rytilahti)
- Leverage data from UDP discovery to initialize device structure [\#132](https://github.com/python-kasa/python-kasa/pull/132) (@dlee1j1)
- Add HS220 hw 2.0 fixture [\#107](https://github.com/python-kasa/python-kasa/pull/107) (@appleguru)

## [0.4.0.dev2](https://github.com/python-kasa/python-kasa/tree/0.4.0.dev2) (2020-11-21)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.4.0.dev1...0.4.0.dev2)

**Implemented enhancements:**

- 'Interface' parameter added to discovery process [\#79](https://github.com/python-kasa/python-kasa/pull/79) (@dmitryelj)

**Fixed bugs:**

- Simplify device class detection for discovery, fix hardcoded timeout [\#112](https://github.com/python-kasa/python-kasa/pull/112) (@rytilahti)
- Update cli.py to addresss crash on year/month calls and improve output formatting [\#103](https://github.com/python-kasa/python-kasa/pull/103) (@BuongiornoTexas)

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

- Release 0.4.0.dev2 [\#118](https://github.com/python-kasa/python-kasa/pull/118) (@rytilahti)
- Pin dependencies on major versions, add poetry.lock [\#94](https://github.com/python-kasa/python-kasa/pull/94) (@rytilahti)

## [0.4.0.dev1](https://github.com/python-kasa/python-kasa/tree/0.4.0.dev1) (2020-07-28)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.4.0.dev0...0.4.0.dev1)

**Implemented enhancements:**

- KL430 support [\#67](https://github.com/python-kasa/python-kasa/issues/67)
- Improve retry logic for discovery, messaging \(was: Handle empty responses\) [\#38](https://github.com/python-kasa/python-kasa/issues/38)
- Add support for lightstrips \(KL430\) [\#74](https://github.com/python-kasa/python-kasa/pull/74) (@rytilahti)

**Documentation updates:**

- Improve poetry usage documentation [\#60](https://github.com/python-kasa/python-kasa/issues/60)

**Closed issues:**

- I don't python... how do I make this executable? [\#88](https://github.com/python-kasa/python-kasa/issues/88)
- ImportError: cannot import name 'smartplug' [\#87](https://github.com/python-kasa/python-kasa/issues/87)
- not able to pip install the library [\#82](https://github.com/python-kasa/python-kasa/issues/82)
- Discover.discover\(\) add selecting network interface \[pull request\] [\#78](https://github.com/python-kasa/python-kasa/issues/78)
- LB100 unable to turn on or off the lights [\#68](https://github.com/python-kasa/python-kasa/issues/68)
- sys\_info not None fails assertion [\#55](https://github.com/python-kasa/python-kasa/issues/55)
- Upload pre-release to pypi for easier testing [\#17](https://github.com/python-kasa/python-kasa/issues/17)

**Merged pull requests:**

- Release 0.4.0.dev1 [\#93](https://github.com/python-kasa/python-kasa/pull/93) (@rytilahti)
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

## [0.4.0.dev0](https://github.com/python-kasa/python-kasa/tree/0.4.0.dev0) (2020-05-27)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.4.0.pre0...0.4.0.dev0)

## [0.4.0.pre0](https://github.com/python-kasa/python-kasa/tree/0.4.0.pre0) (2020-05-27)

[Full Changelog](https://github.com/python-kasa/python-kasa/compare/0.3.5...0.4.0.pre0)

**Implemented enhancements:**

- Add commands to control the wifi settings [\#45](https://github.com/python-kasa/python-kasa/pull/45) (@rytilahti)

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
