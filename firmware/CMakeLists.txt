cmake_minimum_required(VERSION 3.16)

set(SAANOTTS_ROOT "${CMAKE_CURRENT_LIST_DIR}/../third_party/sanoTTS-jp")
if(NOT EXISTS "${SAANOTTS_ROOT}/csrc/saanotts.c")
    message(FATAL_ERROR
        "sanoTTS-jp submodule is missing. Run:\n"
        "  git submodule update --init --recursive")
endif()

set(EXTRA_COMPONENT_DIRS "${SAANOTTS_ROOT}/esp32/components")

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
set(PROJECT_VER "0.1.0")
project(rlcd42_sanotts_demo)

if(NOT SAAN_BOARD_PROBE)
    set(SAAN_ASSET_DIR "${CMAKE_CURRENT_LIST_DIR}/../assets")
    if(NOT DEFINED SAAN_MODEL_BLOB)
        set(SAAN_MODEL_BLOB "${SAAN_ASSET_DIR}/saanotts-jp-v3-int8.bin")
    endif()

    if(NOT EXISTS "${SAAN_MODEL_BLOB}")
        message(FATAL_ERROR
            "Model blob is missing: ${SAAN_MODEL_BLOB}\n"
            "Read licenses/sanoTTS-jp-model.md, then run:\n"
            "  python3 tools/demo.py fetch")
    endif()

    file(SIZE "${SAAN_MODEL_BLOB}" SAAN_MODEL_BLOB_SIZE)
    file(SHA256 "${SAAN_MODEL_BLOB}" SAAN_MODEL_BLOB_SHA256)
    if(NOT SAAN_MODEL_BLOB_SIZE EQUAL 643936)
        message(FATAL_ERROR
            "Unexpected int8 model size: ${SAAN_MODEL_BLOB_SIZE} B (expected 643936 B)")
    endif()
    if(NOT SAAN_MODEL_BLOB_SHA256 STREQUAL
           "c3b89216133fa7bee3f61ed9d8e6c7183a5dfd41b70dab194f42c20fce5b4170")
        message(FATAL_ERROR "Unexpected int8 model SHA-256: ${SAAN_MODEL_BLOB_SHA256}")
    endif()
    message(STATUS "RLCD4.2 sanoTTS model: ${SAAN_MODEL_BLOB} (${SAAN_MODEL_BLOB_SIZE} B)")
    esptool_py_flash_to_partition(flash "model" "${SAAN_MODEL_BLOB}")

    if(SAAN_KANJI)
        if(NOT DEFINED SAAN_DICT_BLOB)
            set(SAAN_DICT_BLOB "${SAAN_ASSET_DIR}/k1-dict-438750.bin")
        endif()
        if(NOT EXISTS "${SAAN_DICT_BLOB}")
            message(FATAL_ERROR
                "Kanji dictionary is missing: ${SAAN_DICT_BLOB}\n"
                "Read the upstream notices, then run:\n"
                "  python3 tools/demo.py fetch --kanji")
        endif()
        file(SIZE "${SAAN_DICT_BLOB}" SAAN_DICT_BLOB_SIZE)
        file(SHA256 "${SAAN_DICT_BLOB}" SAAN_DICT_BLOB_SHA256)
        if(NOT SAAN_DICT_BLOB_SIZE EQUAL 13702320)
            message(FATAL_ERROR
                "Unexpected dictionary size: ${SAAN_DICT_BLOB_SIZE} B (expected 13702320 B)")
        endif()
        if(NOT SAAN_DICT_BLOB_SHA256 STREQUAL
               "f162c922074d76817298b34d8a8fd35f7d195f38540303485a76c956b5d84877")
            message(FATAL_ERROR "Unexpected dictionary SHA-256: ${SAAN_DICT_BLOB_SHA256}")
        endif()
        message(STATUS "RLCD4.2 kanji dictionary: ${SAAN_DICT_BLOB} (${SAAN_DICT_BLOB_SIZE} B)")
        esptool_py_flash_to_partition(flash "dict" "${SAAN_DICT_BLOB}")
    endif()
endif()
