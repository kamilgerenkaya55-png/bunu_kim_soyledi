import asyncio
from main import app, LOCAL_IP, PORT, get_network_info

async def run_tests():
    print("1. Ağ ve IP tespiti test ediliyor...")
    info = await get_network_info()
    print(f"   IP: {info['local_ip']}, Port: {info['port']}")
    assert info["local_ip"] == LOCAL_IP
    assert info["port"] == PORT
    assert "data:image/png;base64," in info["qr_code"]
    print("   ✓ Ağ ve QR kod üretimi başarılı!")

    print("\n2. Oyun yöneticisi durumu test ediliyor...")
    from game_manager import game_manager
    assert game_manager.state == "LOBBY"
    print("   ✓ Başlangıç durumu LOBBY olarak doğrulandı!")

    print("\n✅ TÜM DAHİLİ TESTLER BAŞARIYLA GEÇTİ!")

if __name__ == "__main__":
    asyncio.run(run_tests())
