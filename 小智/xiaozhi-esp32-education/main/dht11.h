#ifndef DHT11_H
#define DHT11_H

#include <stdint.h>
#include "driver/gpio.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize the DHT11 sensor
 * 
 * @param pin The GPIO pin connected to the DHT11 data line
 */
void dht11_init(gpio_num_t pin);

/**
 * @brief Read temperature and humidity from the DHT11 sensor
 * 
 * @param pin The GPIO pin connected to the DHT11 data line
 * @param temperature Pointer to store the temperature in Celsius
 * @param humidity Pointer to store the humidity in %
 * @return 0 on success, or an error code (-1 for timeout/error, -2 for checksum error)
 */
int dht11_read(gpio_num_t pin, float *temperature, float *humidity);

#ifdef __cplusplus
}
#endif

#endif // DHT11_H
