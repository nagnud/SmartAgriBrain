idf_component_register(
    SRCS "src/sensair_iot.c"
    INCLUDE_DIRS "include"
    REQUIRES
        driver
        esp_event
        esp_netif
        esp_timer
        esp_wifi
        json
        mbedtls
        mqtt
        nvs_flash
)

