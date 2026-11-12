import socket
import io
import base64
import qrcode

def get_local_ip() -> str:
    """Yerel ağdaki (Wi-Fi/Ethernet) IP adresini tespit eder."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Gerçek bir bağlantı kurmadan işletim sisteminin aktif ağ arayüzünü bulur
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def generate_qr_base64(data: str) -> str:
    """Verilen URL için base64 formatında QR kod PNG görseli oluşturur."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1e1b4b", back_color="#ffffff")
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{img_b64}"

def print_terminal_qr(data: str):
    """Terminalde de taranabilecek ASCII QR kod yazdırır."""
    try:
        qr = qrcode.QRCode()
        qr.add_data(data)
        qr.print_ascii(invert=True)
    except Exception:
        pass
