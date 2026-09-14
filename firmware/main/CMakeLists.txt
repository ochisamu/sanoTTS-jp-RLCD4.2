if(SAAN_BOARD_PROBE)
    idf_component_register(
        SRCS
            "rlcd42_probe.c"
            "rlcd42_board.c"
            "rlcd42_battery.c"
            "rlcd42_display.c"
        INCLUDE_DIRS "."
        REQUIRES
            driver
            esp_adc
            esp_psram
            esp_timer
            heap
            spi_flash
    )
    message(STATUS "RLCD4.2: model-free board probe (audio/I2S/mic/Wi-Fi excluded)")
else()
    get_filename_component(PROJECT_ROOT "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
    set(SAAN_ROOT "${PROJECT_ROOT}/third_party/sanoTTS-jp")
    set(SAAN_MAIN "${SAAN_ROOT}/esp32/main")

    if(NOT EXISTS "${SAAN_MAIN}/main.c")
        message(FATAL_ERROR "sanoTTS-jp submodule is incomplete: ${SAAN_MAIN}")
    endif()

    set(SAAN_APP_SRCS
        "${SAAN_MAIN}/main.c"
        "${SAAN_MAIN}/saan_model.c"
        "${SAAN_MAIN}/saan_ui_null.c"
        "rlcd42_console.c"
        "rlcd42_entry.c"
        "rlcd42_board.c"
        "rlcd42_battery.c"
        "rlcd42_display.c"
        "rlcd42_saan_i2s.c"
    )

    if(SAAN_KANJI)
        list(APPEND SAAN_APP_SRCS
            "${SAAN_MAIN}/saan_dict.c"
            "${SAAN_MAIN}/saan_kanji.c"
        )
    endif()

    idf_component_register(
        SRCS ${SAAN_APP_SRCS}
        INCLUDE_DIRS "." "${SAAN_MAIN}"
        LDFRAGMENTS "saan_memory.lf"
        REQUIRES
            saanotts_core
            driver
            esp_adc
            esp_mm
            esp_partition
            esp_psram
            esp_timer
            esp_codec_dev
            heap
            spi_flash
    )

    # Run the PA-disable interlock before the upstream app touches the model,
    # dictionary, PSRAM, display, or audio. Keep the pinned submodule byte-for-byte intact by
    # renaming only its app_main symbol at compile time. This must follow component
    # registration because IDF also evaluates this file in CMake script mode while
    # resolving managed-component requirements.
    set_source_files_properties("${SAAN_MAIN}/main.c" PROPERTIES
        COMPILE_DEFINITIONS
            "app_main=saan_upstream_app_main;saan_stream_init=rlcd42_saan_stream_init;saan_stream_pull=rlcd42_saan_stream_pull")
endif()

target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror=return-type)
if(SAAN_BOARD_PROBE)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE SAAN_BOARD_PROBE=1)
else()
    target_compile_definitions(${COMPONENT_LIB} PRIVATE
        RLCD42_SANOTTS_DEMO=1
        SAAN_BOOT_SPEAK=0
        SAAN_AUDIO_PREROLL_SAMPLES=262144
    )
endif()

if(SAAN_ENABLE_PIE AND NOT SAAN_BOARD_PROBE)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE SAAN_INT8_ACT=1)
endif()

if(SAAN_SILENT AND NOT SAAN_BOARD_PROBE)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE SAAN_SKIP_I2S=1)
    message(STATUS "RLCD4.2: silent probe profile (ES8311/I2S/PA compiled out)")
endif()

if(SAAN_KANJI AND NOT SAAN_BOARD_PROBE)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE SAAN_KANJI=1 CHARSET_UTF_8)
endif()
