cmake_minimum_required(VERSION 3.16)
set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/../third_party/sanoTTS-jp/esp32/components")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(rlcd42_stt_mic_probe)
