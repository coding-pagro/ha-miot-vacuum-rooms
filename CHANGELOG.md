# Changelog

## [0.1.0](https://github.com/coding-pagro/ha-miot-vacuum-rooms/compare/v0.1.0...v0.1.0) (2026-11-08)


### Features

* add "Rooms in current run" sensor ([213445f](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/213445f7ae6340707e547f4a7b6c49cfcf4258d3))
* add switch "Use room settings from the app" ([fb107d7](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/fb107d7f1118dcd5229911eb6e7265d7425f67c0)), closes [#4](https://github.com/coding-pagro/ha-miot-vacuum-rooms/issues/4)
* add vacuum entity with safe start, fan speed and area cleaning ([56a6d3a](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/56a6d3a216920a2090c81a15744b5677cb821e15)), closes [#3](https://github.com/coding-pagro/ha-miot-vacuum-rooms/issues/3)
* check sources again on entity registry changes ([24e46cf](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/24e46cf9e1fa3565aa0192632eb45c292ee98ad1))
* **check:** update the WSL venv when requirements_test.txt changes ([18f66fc](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/18f66fcb03ed0e631361aab34cdc1e49657874e7))
* config entry diagnostics with redacted device ID ([6e86e9a](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/6e86e9a0ad497c91643c8fea2c3954d80af9824a))
* **controller:** verify start with retry for clean_rooms and clean_floor ([55c4f1b](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/55c4f1b8556fe5978b69cdeb631c3caced6aa95f))
* heal sources and show repair issues on load ([44ba68a](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/44ba68ab57a5f9111de4fdbcd38fe0cbc28d4201))
* initial MIoT vacuum rooms integration ([acd3873](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/acd3873f3710b86877dc6dbe09939ca6f81e2b1e))
* Raum im Konfigurationsdialog anlernen ([98b148f](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/98b148f12f8e97a517e5e9b09b6e08795cb5def0)), closes [#7](https://github.com/coding-pagro/ha-miot-vacuum-rooms/issues/7)
* remember the Xiaomi device and clear issues on unload ([59f8ed9](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/59f8ed9140fc8f911dda8eb8bb1445b6b3190cc5)), closes [#31](https://github.com/coding-pagro/ha-miot-vacuum-rooms/issues/31)
* Show robot and station problems (error codes) as text ([8c934bb](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/8c934bbfe23fe05516b49049b32f6ef7a9a69a5f)), closes [#10](https://github.com/coding-pagro/ha-miot-vacuum-rooms/issues/10)
* Start-Verifikation mit Retry für clean_rooms und clean_floor ([6975b25](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/6975b25a543121dc343d78ace0fadef8102e368d))
* Stopp beendet offenen Auftrag in der Station ([8c9ffae](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/8c9ffaeda6fcfeceae6e0851981956afb2cfcd80)), closes [#27](https://github.com/coding-pagro/ha-miot-vacuum-rooms/issues/27)
* translate raw clean values into a room display ([72365fa](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/72365faf0cd78f091786f1fdd755db3b3dd9e2d1))
* **vacuum:** hide fan speed in Customised mode, report cleaning mode ([57ed465](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/57ed465c3f4661bdb4cdaf26288324eb1a3a6c2b))
* **vacuum:** show Cleaning at the dock while a job runs ([194d2e0](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/194d2e01eaeea0c5ab5ab1ad5b7b8fba3c999981))


### Bug Fixes

* apply review notes ([e07bb7c](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/e07bb7c61362bc4c71a639b6b2033c9191c0f049)), closes [#5](https://github.com/coding-pagro/ha-miot-vacuum-rooms/issues/5)
* check the job status before room starts ([d96d01f](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/d96d01f060c33e8abba92aa231bd0d9aeeceeac3))
* review findings ([23625da](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/23625da892fc4c217bb88a0f6535fde085201b53))
* Review-Befunde ([734195c](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/734195c6030a59b94b055551c0924e89bab5653d))
* Review-Befunde ([8d3b2c7](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/8d3b2c7ea06f5b6f2fc0a27d22208cadf6414411)), closes [#7](https://github.com/coding-pagro/ha-miot-vacuum-rooms/issues/7)
* Review-Befunde ([541af51](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/541af516301b946690787ede87724f99d9e4be7d))
* Review-Hinweise (OverflowError, README, Tests) ([ddd91b6](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/ddd91b60e71b7a3818e2bb01d2f58996c3c3e5bb)), closes [#10](https://github.com/coding-pagro/ha-miot-vacuum-rooms/issues/10)
* **vacuum:** translate the fan speed label, treat job status None as idle ([a97e127](https://github.com/coding-pagro/ha-miot-vacuum-rooms/commit/a97e127f0e29d4144a08ddda98e5c82c951431a5))
