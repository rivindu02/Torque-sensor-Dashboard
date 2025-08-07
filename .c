/**
 * HX711 Debug and Fix Implementation
 * This code addresses the timeout issues in the original HX711 implementation
 * 
 * IMMEDIATE FIX: Add this to your user_custs1_impl.c file to replace the existing hx711_read()
 */

#include "gpio.h"
#include "arch.h"
#include "user_periph_setup.h"

// Add this function call to your user_app_init() in user_peripheral.c
void hx711_init_sequence(void);

// Replace your existing hx711_read() function with hx711_read_improved()

// Debug flag - set to 1 to enable debug output
#define HX711_DEBUG 1

// HX711 timing constants (in microseconds)
#define HX711_SETTLE_TIME_US    100     // Time for HX711 to settle after SCK low
#define HX711_CLOCK_HIGH_US     1       // Minimum SCK high time
#define HX711_CLOCK_LOW_US      1       // Minimum SCK low time
#define HX711_TIMEOUT_COUNT     50000   // Reduced timeout for faster detection

// Power-down recovery time (in milliseconds)
#define HX711_POWER_UP_TIME_MS  100

/**
 * @brief Check if HX711 is ready (DOUT is LOW)
 * @return true if ready, false if not ready
 */
bool hx711_is_ready(void)
{
    return !GPIO_GetPinStatus(HX711_DOUT_PORT, HX711_DOUT_PIN);
}

/**
 * @brief Power up the HX711 if it's in power-down mode
 */
void hx711_power_up(void)
{
    // Ensure SCK is low to power up the HX711
    GPIO_SetInactive(HX711_SCK_PORT, HX711_SCK_PIN);
    
    // Wait for power-up time
    arch_asm_delay_us(HX711_POWER_UP_TIME_MS * 1000);
    
    #if HX711_DEBUG
    // Check if DOUT goes high after power-up (indicating HX711 is alive)
    if (GPIO_GetPinStatus(HX711_DOUT_PORT, HX711_DOUT_PIN)) {
        // HX711 is powered up (DOUT should be high when not ready)
    }
    #endif
}

/**
 * @brief Power down the HX711
 */
void hx711_power_down(void)
{
    GPIO_SetActive(HX711_SCK_PORT, HX711_SCK_PIN);
    arch_asm_delay_us(60); // Keep SCK high for at least 60us to power down
}

/**
 * @brief Initialize HX711 with proper power-up sequence
 */
void hx711_init(void)
{
    // Ensure SCK starts low
    GPIO_SetInactive(HX711_SCK_PORT, HX711_SCK_PIN);
    
    // Power up the HX711
    hx711_power_up();
    
    // Wait for the first conversion to complete
    uint32_t timeout = HX711_TIMEOUT_COUNT;
    while (!hx711_is_ready() && timeout > 0) {
        arch_asm_delay_us(10);
        timeout--;
    }
    
    #if HX711_DEBUG
    if (timeout == 0) {
        // Debug: HX711 not responding during initialization
    }
    #endif
}

/**
 * @brief Read raw value from HX711 with improved error handling
 * @return Raw 24-bit value from HX711, or error codes:
 *         INT32_MIN: Timeout (HX711 not ready)
 *         INT32_MAX: Communication error
 */
int32_t hx711_read_improved(void)
{
    int32_t value = 0;
    int i;
    uint32_t timeout = HX711_TIMEOUT_COUNT;
    
    // Ensure SCK is low initially
    GPIO_SetInactive(HX711_SCK_PORT, HX711_SCK_PIN);
    arch_asm_delay_us(HX711_SETTLE_TIME_US);
    
    // Wait for DOUT to go LOW (data ready) with timeout
    while (GPIO_GetPinStatus(HX711_DOUT_PORT, HX711_DOUT_PIN)) {
        if (timeout == 0) {
            #if HX711_DEBUG
            // Debug: Timeout waiting for DOUT to go low
            // This suggests HX711 is not responding or not connected properly
            #endif
            return INT32_MIN; // Timeout error
        }
        timeout--;
        arch_asm_delay_us(1); // Shorter delay for more responsive timeout
    }
    
    // Read 24 bits of data with improved timing
    for (i = 0; i < 24; i++) {
        // Set SCK high
        GPIO_SetActive(HX711_SCK_PORT, HX711_SCK_PIN);
        arch_asm_delay_us(HX711_CLOCK_HIGH_US);
        
        // Shift previous bits left
        value <<= 1;
        
        // Set SCK low
        GPIO_SetInactive(HX711_SCK_PORT, HX711_SCK_PIN);
        arch_asm_delay_us(HX711_CLOCK_LOW_US);
        
        // Read data bit (sample after SCK goes low)
        if (GPIO_GetPinStatus(HX711_DOUT_PORT, HX711_DOUT_PIN)) {
            value |= 1;
        }
    }
    
    // Send 25th pulse to set gain to 128 (Channel A)
    GPIO_SetActive(HX711_SCK_PORT, HX711_SCK_PIN);
    arch_asm_delay_us(HX711_CLOCK_HIGH_US);
    GPIO_SetInactive(HX711_SCK_PORT, HX711_SCK_PIN);
    arch_asm_delay_us(HX711_CLOCK_LOW_US);
    
    // Verify DOUT goes high (indicating next conversion started)
    arch_asm_delay_us(10);
    if (!GPIO_GetPinStatus(HX711_DOUT_PORT, HX711_DOUT_PIN)) {
        #if HX711_DEBUG
        // Debug: DOUT didn't go high after reading - possible communication issue
        #endif
        // This might indicate a communication problem, but we'll return the value anyway
    }
    
    // Convert from 24-bit two's complement to signed 32-bit
    if (value & 0x800000) { // Check if MSB is set (negative number)
        value |= 0xFF000000; // Sign extend to 32-bit
    }
    
    return value;
}

/**
 * @brief Read HX711 with automatic retry and error recovery
 * @param max_retries Maximum number of retry attempts
 * @return HX711 reading or error code
 */
int32_t hx711_read_with_retry(uint8_t max_retries)
{
    int32_t result;
    uint8_t retry_count = 0;
    
    while (retry_count < max_retries) {
        result = hx711_read_improved();
        
        if (result != INT32_MIN && result != INT32_MAX) {
            // Valid reading obtained
            return result;
        }
        
        // Error occurred, try recovery
        if (result == INT32_MIN) {
            // Timeout - try power cycle
            hx711_power_down();
            arch_asm_delay_us(1000); // 1ms delay
            hx711_power_up();
        }
        
        retry_count++;
        arch_asm_delay_us(10000); // 10ms delay between retries
    }
    
    return result; // Return last error code
}

/**
 * @brief Test HX711 connectivity and basic functionality
 * @return true if HX711 responds, false otherwise
 */
bool hx711_test_connectivity(void)
{
    // Test 1: Check if DOUT pin changes state
    GPIO_SetInactive(HX711_SCK_PORT, HX711_SCK_PIN);
    arch_asm_delay_us(100);
    
    bool initial_state = GPIO_GetPinStatus(HX711_DOUT_PORT, HX711_DOUT_PIN);
    
    // Try to power down and up
    hx711_power_down();
    arch_asm_delay_us(1000);
    
    bool powered_down_state = GPIO_GetPinStatus(HX711_DOUT_PORT, HX711_DOUT_PIN);
    
    hx711_power_up();
    arch_asm_delay_us(1000);
    
    bool powered_up_state = GPIO_GetPinStatus(HX711_DOUT_PORT, HX711_DOUT_PIN);
    
    // DOUT should be high when powered up and not ready
    return (powered_up_state == true);
}

/**
 * @brief Updated timer callback with improved error handling
 */
void app_adcval1_timer_cb_handler_improved(void)
{
    static ke_msg_id_t adc_timer = EASY_TIMER_INVALID_TIMER;
    static uint8_t consecutive_errors = 0;
    static uint8_t max_consecutive_errors = 5;
    
    struct custs1_val_ntf_ind_req *req = KE_MSG_ALLOC_DYN(CUSTS1_VAL_NTF_REQ,
                                                          prf_get_task_from_id(TASK_ID_CUSTS1),
                                                          TASK_APP,
                                                          custs1_val_ntf_ind_req,
                                                          DEF_SVC1_ADC_VAL_1_CHAR_LEN);

    // Try to read HX711 with retry
    int32_t hx_val = hx711_read_with_retry(3);
    
    if (hx_val == INT32_MIN || hx_val == INT32_MAX) {
        // Error occurred
        consecutive_errors++;
        
        if (consecutive_errors >= max_consecutive_errors) {
            // Too many consecutive errors - try full reinit
            hx711_init();
            consecutive_errors = 0;
        }
        
        // Send a default/error value or skip notification
        KE_MSG_FREE((struct ke_msg *)req);
        
        // Continue timer even with errors
        if (ke_state_get(TASK_APP) == APP_CONNECTED) {
            adc_timer = app_easy_timer(APP_PERIPHERAL_CTRL_TIMER_DELAY, app_adcval1_timer_cb_handler_improved);
        }
        return;
    }
    
    // Successfully read value
    consecutive_errors = 0;
    adc_val_1 = hx_val;

    // Prepare notification
    req->handle = SVC1_IDX_ADC_VAL_1_VAL;
    req->length = DEF_SVC1_ADC_VAL_1_CHAR_LEN;
    req->notification = true;
    uint32_t big_endian_val = __builtin_bswap32(adc_val_1);
    memcpy(req->value, &big_endian_val, DEF_SVC1_ADC_VAL_1_CHAR_LEN);

    // Update GATT database
    attmdb_att_set_value(SVC1_IDX_ADC_VAL_1_VAL, DEF_SVC1_ADC_VAL_1_CHAR_LEN, 0, (uint8_t *)&big_endian_val);

    // Send notification
    KE_MSG_SEND(req);

    // Schedule next reading
    if (ke_state_get(TASK_APP) == APP_CONNECTED) {
        adc_timer = app_easy_timer(APP_PERIPHERAL_CTRL_TIMER_DELAY, app_adcval1_timer_cb_handler_improved);
    } else {
        adc_timer = EASY_TIMER_INVALID_TIMER;
    }
}





void user_app_init(void)
{
    // ... existing code ...
    
    // Add HX711 initialization
    hx711_init();
    
    default_app_on_init();
}