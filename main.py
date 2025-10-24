"""
Main application for receiving PVM LoRa packets
"""

import time
import threading
from gpiozero import LED
from SX127x.board_config import BOARD
from SX127x.LoRa import MODE, BW, CODING_RATE
from LoRa import LoRaPacket

# --- Periodic Send Thread ---
def periodic_send_thread(lora, device_id, interval=30, stop_event=None):
    """
    Thread function to periodically send keepalive packets
    
    Args:
        lora: LoRaPacket instance
        device_id: Device ID for this sender
        interval: Seconds between transmissions
        stop_event: threading.Event to signal when to stop
    """
    print(f"Periodic TX enabled (every {interval}s, Device ID: {device_id})")
    
    packet_count = 0
    while not (stop_event and stop_event.is_set()):
        try:
            timestamp_str = lora.get_timestamp()
            packet = lora.create_packet(
                device_id=device_id,
                packet_type=1,
                priority=2,
                payload_str="DUMMY DATA",
                timestamp_str=timestamp_str
            )
            
            packet_count += 1
            print(f"TX #{packet_count} at {time.strftime('%H:%M:%S')}")
            lora.send_packet(packet)
            time.sleep(0.5)
            
            lora.set_mode(MODE.SLEEP)
            lora.reset_ptr_rx()
            lora.set_mode(MODE.RXCONT)
            
        except Exception as e:
            print(f"TX error: {e}")
        
        for _ in range(interval):
            if stop_event and stop_event.is_set():
                break
            time.sleep(1)

# --- Main Application ---
if __name__ == "__main__":
    # --- GPIO and Hardware Initialization ---
    try:
        rx_led = LED(23)
        sos_led = LED(19)
        BOARD.setup()
    except Exception as e:
        print(f"Hardware initialization failed: {e}")
        exit()
    
    # Configuration
    DEVICE_ID = 10010
    SEND_INTERVAL = 20
    ENABLE_PERIODIC_SEND = False
    VERBOSE = True
    
    lora = LoRaPacket(rx_led=rx_led, sos_led=sos_led, verbose=VERBOSE)
    
    try:
        print("="*60)
        print("PPM Initialization")
        print(f"Device ID: {DEVICE_ID}")
        print("="*60)
        
        lora.configure_for_pvm(
            freq=433.0,
            sf=7,
            bw=BW.BW125,
            cr=CODING_RATE.CR4_5,
            sync_word=0xA5,
            explicit_header=True,
            crc_on=True
        )
        
        lora.start_listening()
        
        # Start periodic send thread if enabled
        stop_event = threading.Event()
        send_thread = None
        
        if ENABLE_PERIODIC_SEND:
            send_thread = threading.Thread(
                target=periodic_send_thread,
                args=(lora, DEVICE_ID, SEND_INTERVAL, stop_event),
                daemon=True
            )
            send_thread.start()
        
        print("="*60)
        
        # Keep running and print periodic status
        last_check = time.time()
        start_time = time.time()
        while True:
            time.sleep(0.1)
            
            if time.time() - last_check > 60:
                elapsed = int(time.time() - start_time)
                print(f"[{time.strftime('%H:%M:%S')}] Runtime: {elapsed//60}m {elapsed%60}s | "
                      f"Packets: {lora.packet_count}")
                last_check = time.time()
            
    except KeyboardInterrupt:
        print(f"\nStopped (Total packets: {lora.packet_count})")
        
        if ENABLE_PERIODIC_SEND and send_thread:
            stop_event.set()
            send_thread.join(timeout=2)
            
    finally:
        lora.set_mode(MODE.SLEEP)
        BOARD.teardown()
        rx_led.close()
        sos_led.close()
        lora.influx.close()