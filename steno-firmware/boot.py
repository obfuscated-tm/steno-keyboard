import usb_hid
import usb_cdc

usb_cdc.enable(console=True, data=True)

GEMINI_PR_DESCRIPTOR = bytes((
    0x06, 0x50, 0xFF,  # Usage Page (Vendor Defined 0xFF50)
    0x0A, 0x01, 0x00,  # Usage (0x0001)
    0xA1, 0x01,        # Collection (Application)
    0x85, 0x01,        # Report ID (1)
    0x09, 0x01,        # Usage (0x01)  <-- this was missing
    0x15, 0x00,        # Logical Minimum (0)
    0x25, 0xFF,        # Logical Maximum (255)
    0x75, 0x08,        # Report Size (8)
    0x95, 0x06,        # Report Count (6)
    0x81, 0x02,        # Input (Data,Var,Abs)
    0xC0               # End Collection
))

steno_device = usb_hid.Device(
    report_descriptor=GEMINI_PR_DESCRIPTOR,
    usage_page=0xFF50,
    usage=0x01,
    report_ids=(1,),
    in_report_lengths=(6,),
    out_report_lengths=(0,),
)

usb_hid.enable((steno_device,))