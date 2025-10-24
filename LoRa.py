"""
LoRa module for receiving and parsing PVM custom packets
"""

import struct
import time
from SX127x.LoRa import *
from SX127x.board_config import BOARD
from InfluxDB import InfluxDBManager

# --- Custom LoRa Class ---
class LoRaPacket(LoRa):
    """
    Custom LoRa class for receiving and sending PVM packets
    
    This class handles all LoRa operations including:
    - Packet creation and parsing
    - CRC calculation and verification
    - Transmission and reception
    - LED indicators
    """
    
    # Packet structure constants
    PACKET_SIZE = 126
    PAYLOAD_SIZE = 100
    TIMESTAMP_SIZE = 20
    
    # Packet types
    TYPE_GPS = 0x01
    TYPE_SOS = 0x02
    TYPE_KEEPALIVE = 0x03
    
    def __init__(self, rx_led=None, sos_led=None, verbose=False, enable_influxdb=True):
        """
        Initialize LoRaPacket instance
        
        Args:
            rx_led: LED object for RX indication
            sos_led: LED object for TX indication
            verbose: Enable verbose output
        """
        super(LoRaPacket, self).__init__(False)
        self.rx_led = rx_led
        self.sos_led = sos_led
        self.packet_count = 0
        self.set_mode(MODE.SLEEP)
        self.set_dio_mapping([0, 0, 0, 0, 0, 0])

        # Initialize InfluxDB connection
        self.enable_influxdb = enable_influxdb
        self.influx = InfluxDBManager() if enable_influxdb else None
    
    @staticmethod
    def calculate_crc16(data):
        """
        Calculate CRC-16 matching the ESP32 implementation
        
        Args:
            data: Bytes to calculate CRC for
            
        Returns:
            uint16_t CRC value
        """
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc
    
    def create_packet(self, device_id, packet_type, priority, payload_str="", timestamp_str=""):
        """
        Create a PVM packet with the same structure as ESP32
        
        Args:
            device_id: uint16_t device ID
            packet_type: uint8_t packet type (0x01=GPS, 0x02=SOS, 0x03=KEEPALIVE)
            priority: uint8_t priority (0=normal, 1=high)
            payload_str: string payload (max 100 chars, will be padded/truncated)
            timestamp_str: string timestamp (max 20 chars, will be padded/truncated)
        
        Returns:
            bytes: 126-byte packet ready to transmit
        """
        # Ensure payload is exactly 100 bytes
        payload_bytes = payload_str.encode('utf-8')[:self.PAYLOAD_SIZE]
        payload_bytes = payload_bytes.ljust(self.PAYLOAD_SIZE, b'\x00')
        
        # Ensure timestamp is exactly 20 bytes
        timestamp_bytes = timestamp_str.encode('utf-8')[:self.TIMESTAMP_SIZE]
        timestamp_bytes = timestamp_bytes.ljust(self.TIMESTAMP_SIZE, b'\x00')
        
        # Pack the packet (without CRC first)
        packet_without_crc = struct.pack(
            '<HBB100s20s',
            device_id, packet_type, priority, payload_bytes, timestamp_bytes
        )
        
        # Calculate CRC on the packet without CRC
        crc = self.calculate_crc16(packet_without_crc)
        
        # Pack complete packet with CRC
        complete_packet = struct.pack(
            '<HBB100s20sH',
            device_id, packet_type, priority, payload_bytes, timestamp_bytes, crc
        )
        
        return complete_packet
    
    def parse_packet(self, payload):
        """
        Parse custom PVM packet structure
        
        Args:
            payload: Raw bytes received
            
        Returns:
            dict with packet info or None if invalid
        """
        if len(payload) != self.PACKET_SIZE:
            print(f"Invalid packet size: {len(payload)} (expected {self.PACKET_SIZE})")
            return None
        
        try:
            # Unpack packet
            device_id, pkt_type, priority, pkt_payload, pkt_timestamp, received_crc = \
                struct.unpack('<HBB100s20sH', bytes(payload))
            
            # Verify CRC (calculate on everything except the last 2 bytes)
            packet_data_for_crc = bytes(payload[:124])
            calculated_crc = self.calculate_crc16(packet_data_for_crc)

            if calculated_crc != received_crc:
                print(f"CRC mismatch! Calculated: 0x{calculated_crc:04X}, Received: 0x{received_crc:04X}")
                print(f"   Packet bytes (first 20): {' '.join(f'{b:02X}' for b in payload[:20])}")
                print(f"   Packet bytes (last 10):  {' '.join(f'{b:02X}' for b in payload[-10:])}")
                # return None
            
            # Decode payload and timestamp (remove null terminators)
            pkt_payload_str = pkt_payload.decode('utf-8', 'ignore').rstrip('\x00')
            pkt_timestamp_str = pkt_timestamp.decode('utf-8', 'ignore').rstrip('\x00')
            
            # Get type name
            type_names = {
                self.TYPE_GPS: 'GPS',
                self.TYPE_SOS: 'SOS',
                self.TYPE_KEEPALIVE: 'KEEPALIVE'
            }
            type_name = type_names.get(pkt_type, 'Unknown')
            
            packet_info = {
                'device_id': device_id,
                'type': pkt_type,
                'type_name': type_name,
                'priority': priority,
                'payload': pkt_payload_str,
                'timestamp': pkt_timestamp_str,
                'crc': received_crc,
                'crc_valid': True
            }
            
            return packet_info
            
        except Exception as e:
            print(f"Error parsing packet: {e}")
            return None
    
    def print_packet(self, packet_info, rssi):
        """
        Print formatted PVM packet information
        
        Args:
            packet_info: Dictionary with packet data
            rssi: RSSI value in dBm
        """
        print(f"\nDeviceID: {packet_info['device_id']} | "
              f"Type: {packet_info['type_name']} | "
              f"Priority: {packet_info['priority']} | "
              f"Payload: {packet_info['payload']} | ")
        print(f"Timestamp: {packet_info['timestamp']} | "
              f"CRC: {hex(packet_info['crc'])} | RSSI: {rssi} dBm")
    
    def send_packet(self, packet_bytes):
        """
        Send a packet via LoRa
        
        Args:
            packet_bytes: bytes to send
        """
        self.set_mode(MODE.STDBY)
        self.write_payload(list(packet_bytes))
        self.set_mode(MODE.TX)
        
        if self.verbose:
            print(f"Sent {len(packet_bytes)} bytes")
            packet_info = self.parse_packet(packet_bytes)
            if packet_info:
                self.print_packet(packet_info, self.get_pkt_rssi_value())
    
    def get_timestamp(self):
        """
        Get current timestamp in PVM format (DD-MM-YYYY HH:MM:S)
        
        Returns:
            str: Formatted timestamp
        """
        current_time = time.localtime()
        return time.strftime('%d-%m-%Y %H:%M:%S', current_time)

    def on_rx_done(self):
        """
        Callback when a packet is received
        Handles packet parsing, LED indication, and mode switching
        """
        self.packet_count += 1
        self.clear_irq_flags(RxDone=1)
        payload = self.read_payload(nocheck=True)
        rssi = self.get_pkt_rssi_value()
        
        packet_info = self.parse_packet(payload)
        
        if packet_info:
            self.print_packet(packet_info, rssi)
            self._indicate_packet_received(packet_info['type'])

            # Insert into InfluxDB
            if self.enable_influxdb and self.influx:
                latitude, longitude, altitude = self._parse_gps_payload(packet_info['payload'])
                
                try:
                    tags = {"device_id": packet_info['device_id']}
                    fields = {
                        "priority": packet_info['priority'],
                        "latitude": latitude,
                        "longitude": longitude,
                        "altitude": altitude,
                        "sos_signal": packet_info['type'] == self.TYPE_SOS
                    }
                    
                    if self.influx.insert_into_influxdb(
                        measurement="gps-data", 
                        tags=tags, 
                        fields=fields, 
                        timestamp=packet_info['timestamp']
                    ):
                        if self.verbose:
                            print("Saved to InfluxDB")
                except Exception as e:
                    print(f"InfluxDB error: {e}")
        else:
            print(f"Failed to parse packet ({len(payload)} bytes)")
            if self.rx_led:
                self.rx_led.blink(on_time=0.05, off_time=0.05, n=3, background=True)
        
        # Return to receive mode
        self.set_mode(MODE.SLEEP)
        self.reset_ptr_rx()
        self.set_mode(MODE.RXCONT)
    
    def _parse_gps_payload(self, payload_str):
        """
        Parse GPS coordinates from payload string
        
        Args:
            payload_str: Payload string in format "lat,lon" or "lat,lon,alt"
            
        Returns:
            tuple: (latitude, longitude, altitude)
        """
        try:
            if payload_str and ',' in payload_str:
                parts = payload_str.split(',')
                latitude = float(parts[0])
                longitude = float(parts[1])
                altitude = float(parts[2]) if len(parts) >= 3 else 0.0
            else:
                # Default dummy values when GPS data unavailable
                latitude = None
                longitude = None
                altitude = None
            return latitude, longitude, altitude
        except (ValueError, IndexError):
            return None, None, None
    
    def _indicate_packet_received(self, packet_type):
        """
        Blink LED based on packet type
        
        Args:
            packet_type: Type of packet received
        """
        if packet_type == self.TYPE_SOS:
            if self.sos_led:
                self.sos_led.blink(on_time=0.3, off_time=0.3, n=3, background=True)
        elif packet_type == self.TYPE_GPS:
            if self.rx_led:
                self.rx_led.blink(on_time=0.3, off_time=0.3, n=3, background=True)
        elif packet_type == self.TYPE_KEEPALIVE:
            if self.rx_led:
                self.rx_led.blink(on_time=0.2, off_time=0.2, n=2, background=True)
        else:
            if self.rx_led:
                self.rx_led.blink(on_time=0.5, off_time=0.5, n=1, background=True)

    def on_tx_done(self):
        """
        Callback when a packet transmission is complete
        """
        if self.verbose:
            print("Packet sent")
        self.clear_irq_flags(TxDone=1)
        self.set_mode(MODE.SLEEP)
        self.reset_ptr_rx()
        self.set_mode(MODE.RXCONT)

    def configure_for_pvm(self, freq=433.0, sf=7, bw=BW.BW125, cr=CODING_RATE.CR4_5, 
                          sync_word=0xA5, explicit_header=True, crc_on=True):
        """
        Configure LoRa parameters to match PVM ESP32 settings
        
        Args:
            freq: Frequency in MHz (default: 433.0)
            sf: Spreading factor (default: 7)
            bw: Bandwidth (default: BW.BW125)
            cr: Coding rate (default: CODING_RATE.CR4_5)
            sync_word: Sync word (default: 0xA5)
            explicit_header: Use explicit header mode (default: True)
            crc_on: Enable CRC checking (default: True)
        """
        self.set_mode(MODE.SLEEP)
        
        self.set_freq(freq)
        self.set_pa_config(pa_select=1, max_power=0x0F, output_power=0x0F)
        self.set_sync_word(sync_word)
        self.set_spreading_factor(sf)
        self.set_bw(bw)
        self.set_coding_rate(cr)
        self.set_payload_length(self.PACKET_SIZE)
        
        if not explicit_header:
            self.set_implicit_header_mode()
            self.set_payload_length(self.PACKET_SIZE)
        
        self.set_rx_crc(crc_on)
        self.set_preamble(8)
        self.set_agc_auto_on(True)
        self.set_lna_gain(GAIN.G1)
        
        print(f"LoRa configured: {freq} MHz, SF{sf}, BW125, Sync=0x{sync_word:02X}")

    def start_listening(self):
        """
        Start continuous receive mode
        """
        self.set_mode(MODE.RXCONT)
        print("Listening for packets...")
    
    def stop_listening(self):
        """
        Stop listening and enter sleep mode
        """
        self.set_mode(MODE.SLEEP)