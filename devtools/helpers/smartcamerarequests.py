"""Module for smart camera requests."""

from __future__ import annotations

SMARTCAMERA_REQUESTS: list[dict] = [
    {"getAlertTypeList": {"msg_alarm": {"name": "alert_type"}}},
    {"getNightVisionCapability": {"image_capability": {"name": ["supplement_lamp"]}}},
    {"getDeviceInfo": {"device_info": {"name": ["basic_info"]}}},
    {"getDetectionConfig": {"motion_detection": {"name": ["motion_det"]}}},
    {"getPersonDetectionConfig": {"people_detection": {"name": ["detection"]}}},
    {"getVehicleDetectionConfig": {"vehicle_detection": {"name": ["detection"]}}},
    {"getBCDConfig": {"sound_detection": {"name": ["bcd"]}}},
    {"getPetDetectionConfig": {"pet_detection": {"name": ["detection"]}}},
    {"getBarkDetectionConfig": {"bark_detection": {"name": ["detection"]}}},
    {"getMeowDetectionConfig": {"meow_detection": {"name": ["detection"]}}},
    {"getGlassDetectionConfig": {"glass_detection": {"name": ["detection"]}}},
    {"getTamperDetectionConfig": {"tamper_detection": {"name": "tamper_det"}}},
    {"getLensMaskConfig": {"lens_mask": {"name": ["lens_mask_info"]}}},
    {"getLdc": {"image": {"name": ["switch", "common"]}}},
    {"getLastAlarmInfo": {"system": {"name": ["last_alarm_info"]}}},
    {"getLedStatus": {"led": {"name": ["config"]}}},
    {"getTargetTrackConfig": {"target_track": {"name": ["target_track_info"]}}},
    {"getPresetConfig": {"preset": {"name": ["preset"]}}},
    {"getFirmwareUpdateStatus": {"cloud_config": {"name": "upgrade_status"}}},
    {"getMediaEncrypt": {"cet": {"name": ["media_encrypt"]}}},
    {"getConnectionType": {"network": {"get_connection_type": []}}},
    {
        "getAlertConfig": {
            "msg_alarm": {
                "name": ["chn1_msg_alarm_info", "capability"],
                "table": ["usr_def_audio"],
            }
        }
    },
    {"getAlertPlan": {"msg_alarm_plan": {"name": "chn1_msg_alarm_plan"}}},
    {"getSirenTypeList": {"siren": {}}},
    {"getSirenConfig": {"siren": {}}},
    {"getLightTypeList": {"msg_alarm": {}}},
    {"getSirenStatus": {"siren": {}}},
    {"getLightFrequencyInfo": {"image": {"name": "common"}}},
    {"getRotationStatus": {"image": {"name": ["switch"]}}},
    {"getNightVisionModeConfig": {"image": {"name": "switch"}}},
    {"getWhitelampStatus": {"image": {"get_wtl_status": ["null"]}}},
    {"getWhitelampConfig": {"image": {"name": "switch"}}},
    {"getMsgPushConfig": {"msg_push": {"name": ["chn1_msg_push_info"]}}},
    {"getSdCardStatus": {"harddisk_manage": {"table": ["hd_info"]}}},
    {"getCircularRecordingConfig": {"harddisk_manage": {"name": "harddisk"}}},
    {"getRecordPlan": {"record_plan": {"name": ["chn1_channel"]}}},
    {"getAudioConfig": {"audio_config": {"name": ["speaker", "microphone"]}}},
    {"getFirmwareAutoUpgradeConfig": {"auto_upgrade": {"name": ["common"]}}},
    {"getVideoQualities": {"video": {"name": ["main"]}}},
    {"getVideoCapability": {"video_capability": {"name": "main"}}},
    {"getTimezone": {"system": {"name": "basic"}}},
    {"getClockStatus": {"system": {"name": "clock_status"}}},
    # single request only methods
    {"get": {"function": {"name": ["module_spec"]}}},
    {"get": {"cet": {"name": ["vhttpd"]}}},
    {"get": {"motor": {"name": ["capability"]}}},
    {"get": {"audio_capability": {"name": ["device_speaker", "device_microphone"]}}},
    {"get": {"audio_config": {"name": ["speaker", "microphone"]}}},
]
