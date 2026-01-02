import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import json
from datetime import datetime

# BOT AYARLARI
TOKEN = 'MTQzMTk1NTAzMTA4NjYwMDIzNA.G3AgTA.o8NwOj66KJRgYcw8ppRoVMwkh96yYqTfgCXW-U'
GUILD_ID = 1429103322001833985
ADMIN_ROLE_ID = 1429103391069569186
API_URL = "https://vahsetapiservices365.onrender.com/api/user/"

# Bot ayarları
BOT_NAME = "Vahset Intelligence"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="/", intents=intents, help_command=None)

# Veritabanı dosyaları
CREDITS_FILE = "credits.json"
SORGULAR_FILE = "sorgular.json"

# Kredi sistemi
user_credits = {}
aktif_sorgular = {}  # {message_id: {"user_id": 123, "modal": True/False}}

def load_credits():
    """Kredi verilerini yükle"""
    try:
        with open(CREDITS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_credits():
    """Kredi verilerini kaydet"""
    try:
        with open(CREDITS_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_credits, f, indent=4, ensure_ascii=False)
    except:
        pass

def load_sorgular():
    """Sorgu geçmişini yükle"""
    try:
        with open(SORGULAR_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"sorgular": []}

def save_sorgular():
    """Sorgu geçmişini kaydet"""
    try:
        with open(SORGULAR_FILE, 'w', encoding='utf-8') as f:
            json.dump(aktif_sorgular, f, indent=4, ensure_ascii=False)
    except:
        pass

user_credits = load_credits()
sorgu_gecmisi = load_sorgular()

class CreditSystem:
    @staticmethod
    def get_credits(user_id):
        return user_credits.get(str(user_id), 0)

    @staticmethod
    def use_credit(user_id):
        user_id_str = str(user_id)
        if user_id_str in user_credits and user_credits[user_id_str] > 0:
            user_credits[user_id_str] -= 1
            save_credits()
            return True, user_credits[user_id_str]
        return False, 0

    @staticmethod
    def add_credits(user_id, amount):
        user_id_str = str(user_id)
        if user_id_str in user_credits:
            user_credits[user_id_str] += amount
        else:
            user_credits[user_id_str] = amount
        save_credits()
        return user_credits[user_id_str]

class SorguModal(discord.ui.Modal, title="🔍 Sorgu Yap"):
    """Sorgu yapma modalı"""

    discord_id = discord.ui.TextInput(
        label="Discord ID",
        placeholder="801174548883832832",
        style=discord.TextStyle.short,
        required=True,
        min_length=17,
        max_length=20
    )

    def __init__(self, message_id):
        super().__init__()
        self.message_id = message_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)

        user_id = self.discord_id.value.strip()

        # Hak kontrolü
        user_credits_left = CreditSystem.get_credits(interaction.user.id)

        if user_credits_left <= 0:
            embed = discord.Embed(
                title="❌ Yetersiz Hak",
                description="Sorgu yapmak için yeterli hakkınız kalmadı!",
                color=0xff0000
            )
            embed.add_field(
                name="Bilgi",
                value="Kalan hak: 0\nAdmin ile iletişime geçin.",
                inline=False
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # ID kontrolü
        if not user_id.isdigit() or len(user_id) < 17:
            embed = discord.Embed(
                title="⚠️ Geçersiz ID",
                description="18 haneli Discord ID girin.",
                color=0xff9900
            )
            embed.add_field(
                name="Örnek",
                value="`801174548883832832`",
                inline=False
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # API'den veri çek
        user_data = await get_user_data_from_api(user_id)

        if not user_data:
            # API çalışmıyorsa hakkı geri ver
            CreditSystem.add_credits(interaction.user.id, 1)

            embed = discord.Embed(
                title="❌ API Hatası",
                description="API şu anda çalışmıyor.",
                color=0xff0000
            )
            embed.add_field(
                name="Bilgi",
                value="Lütfen daha sonra tekrar deneyin.",
                inline=False
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Email ve IP'yi al
        email = user_data.get('Email', 'Bulunamadı')
        ip_address = user_data.get('IP Adres', 'Bulunamadı')

        # Eğer API farklı key kullanıyorsa
        if email == 'Bulunamadı':
            email = user_data.get('email', 'Bulunamadı')

        if ip_address == 'Bulunamadı':
            ip_address = user_data.get('ip', 'Bulunamadı')
            ip_address = user_data.get('ip_address', ip_address)

        # IP'den Google Maps linki al
        maps_link, location_text = await get_ip_location(ip_address)

        # Hak kullan
        success, new_credits = CreditSystem.use_credit(interaction.user.id)

        if not success:
            embed = discord.Embed(
                title="❌ Sistem Hatası",
                description="Hak kullanımı sırasında hata oluştu!",
                color=0xff0000
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Embed oluştur
        embed = create_sorgu_embed(email, ip_address, interaction.user, user_id, maps_link, location_text, new_credits)

        # Sonucu sadece kullanıcıya gönder
        await interaction.followup.send(embed=embed, ephemeral=True)

        # Sorguyu kaydet
        sorgu_kaydet(interaction.user.id, user_id, email, ip_address)

class SorguView(discord.ui.View):
    """Sorgu paneli view'ı"""

    def __init__(self, message_id):
        super().__init__(timeout=None)
        self.message_id = message_id

    @discord.ui.button(label="🔍 Sorgu Yap", style=discord.ButtonStyle.primary, emoji="📝", custom_id="sorgu_yap")
    async def sorgu_yap_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Hak kontrolü
        user_credits_left = CreditSystem.get_credits(interaction.user.id)

        if user_credits_left <= 0:
            embed = discord.Embed(
                title="❌ Yetersiz Hak",
                description="Sorgu yapmak için yeterli hakkınız kalmadı!",
                color=0xff0000
            )
            embed.add_field(
                name="Bilgi",
                value="Kalan hak: 0\nAdmin ile iletişime geçin.",
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Modal aç
        modal = SorguModal(self.message_id)
        await interaction.response.send_modal(modal)

@bot.event
async def on_ready():
    print(f'✅ {BOT_NAME} Botu Aktif!')
    print(f'🤖 Bot: {bot.user}')
    print(f'🏠 Sunucu ID: {GUILD_ID}')

    try:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        print(f'✅ Komutlar senkronize edildi!')
    except Exception as e:
        print(f'❌ Hata: {e}')

async def get_user_data_from_api(user_id):
    """API'den veri çek"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_URL}{user_id}", headers=headers, timeout=15, ssl=False) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return None
    except:
        return None

async def get_ip_location(ip_address):
    """IP'den konum bilgisi al ve Google Maps linki oluştur"""
    if not ip_address or ip_address == 'Bulunamadı' or ip_address == 'N/A':
        return None, None

    try:
        async with aiohttp.ClientSession() as session:
            # IP-API servisi
            try:
                url = f"http://ip-api.com/json/{ip_address}?fields=status,country,city,lat,lon,isp"
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('status') == 'success':
                            lat = data.get('lat')
                            lon = data.get('lon')
                            city = data.get('city', '')
                            country = data.get('country', '')

                            # Google Maps linki oluştur
                            if lat and lon:
                                maps_link = f"https://www.google.com/maps?q={lat},{lon}"
                                location_text = f"{city}, {country}" if city and country else "Konum bulundu"
                                return maps_link, location_text
            except:
                pass

            # Alternative service
            try:
                url = f"https://ipinfo.io/{ip_address}/json"
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'loc' in data:
                            loc = data['loc'].split(',')
                            if len(loc) == 2:
                                lat, lon = loc
                                maps_link = f"https://www.google.com/maps?q={lat},{lon}"
                                city = data.get('city', '')
                                country = data.get('country', '')
                                location_text = f"{city}, {country}" if city and country else "Konum bulundu"
                                return maps_link, location_text
            except:
                pass

    except:
        pass

    return None, None

def create_sorgu_embed(email, ip_address, requester, target_id, maps_link=None, location_text=None, kalan_hak=None):
    """Sorgu embed'i oluştur"""

    embed = discord.Embed(
        title="🔍 VAHŞET INTELLIGENCE - SORGULAMA SONUCU",
        color=0x8B0000
    )

    # Email bilgisi
    embed.add_field(
        name="📧 EMAİL",
        value=f"```{email}```",
        inline=False
    )

    # IP bilgisi
    embed.add_field(
        name="🌐 IP ADRESİ",
        value=f"```{ip_address}```",
        inline=False
    )

    # Google Maps linki
    if maps_link and location_text:
        embed.add_field(
            name="📍 KONUM BİLGİSİ",
            value=f"**Yaklaşık Konum:** {location_text}\n**Google Maps:** [📍 Haritada Görüntüle]({maps_link})",
            inline=False
        )
    elif maps_link:
        embed.add_field(
            name="📍 KONUM BİLGİSİ",
            value=f"**Google Maps:** [📍 Haritada Görüntüle]({maps_link})",
            inline=False
        )
    elif ip_address != 'Bulunamadı' and ip_address != 'N/A':
        embed.add_field(
            name="📍 KONUM BİLGİSİ",
            value="Konum bilgisi alınamadı",
            inline=False
        )

    # Kalan hak (opsiyonel)
    if kalan_hak is not None:
        embed.set_footer(text=f"{BOT_NAME} • Sadece siz görüyorsunuz • Kalan hak: {kalan_hak}")
    else:
        embed.set_footer(text=f"{BOT_NAME} • Sadece siz görüyorsunuz")

    return embed

def sorgu_kaydet(kullanici_id, sorgulanan_id, email, ip):
    """Sorguyu kaydet"""
    sorgu = {
        "tarih": datetime.now().isoformat(),
        "kullanici_id": str(kullanici_id),
        "sorgulanan_id": sorgulanan_id,
        "email": email,
        "ip": ip
    }

    sorgu_gecmisi["sorgular"].append(sorgu)

    # Son 100 sorguyu sakla
    if len(sorgu_gecmisi["sorgular"]) > 100:
        sorgu_gecmisi["sorgular"] = sorgu_gecmisi["sorgular"][-100:]

    try:
        with open(SORGULAR_FILE, 'w', encoding='utf-8') as f:
            json.dump(sorgu_gecmisi, f, indent=4, ensure_ascii=False)
    except:
        pass

@bot.tree.command(name="sorgu_paneli", description="Sorgu panelini aç (Admin)")
async def sorgu_paneli(interaction: discord.Interaction):
    """Sorgu panelini aç - SADECE ADMIN"""

    # Admin kontrolü
    admin_role = interaction.guild.get_role(ADMIN_ROLE_ID)
    if not admin_role or admin_role not in interaction.user.roles:
        embed = discord.Embed(
            title="❌ Yetkisiz",
            description="Bu komutu kullanmak için admin değilsiniz!",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Panel embed'i oluştur
    embed = discord.Embed(
        title="🔍 VAHŞET INTELLIGENCE - SORGU PANELİ",
        description="**Aşağıdaki butona tıklayarak sorgu yapabilirsiniz.**",
        color=0x8B0000
    )

    embed.add_field(
        name="📋 NASIL KULLANILIR?",
        value="1. **🔍 Sorgu Yap** butonuna tıklayın\n"
              "2. Açılan pencerede Discord ID girin\n"
              "3. Sonuç sadece size özel olarak gösterilir",
        inline=False
    )

    embed.add_field(
        name="⚙️ SİSTEM BİLGİSİ",
        value=f"• Her sorgu **1 hak** kullanır\n"
              f"• Sonuçlar **sadece siz görürsünüz**\n"
              f"• **Email, IP ve Google Maps** linki gösterilir\n"
              f"• Bot: {BOT_NAME}",
        inline=False
    )

    embed.add_field(
        name="👤 PANEL AÇAN",
        value=interaction.user.mention,
        inline=True
    )

    embed.add_field(
        name="📅 TARİH",
        value=datetime.now().strftime("%d/%m/%Y %H:%M"),
        inline=True
    )

    embed.set_footer(text=f"{BOT_NAME} • Güvenli Sorgu Sistemi")

    # View oluştur
    view = SorguView(interaction.id)

    # Mesajı gönder
    await interaction.response.send_message(embed=embed, view=view)

    # Mesaj ID'sini kaydet
    message = await interaction.original_response()
    aktif_sorgular[str(message.id)] = {
        "user_id": interaction.user.id,
        "modal": True
    }

@bot.tree.command(name="hak_ver", description="Kullanıcıya sorgu hakkı ekle")
@app_commands.describe(
    user="Hak verilecek kullanıcı",
    amount="Eklenecek hak miktarı"
)
async def hak_ver(interaction: discord.Interaction, user: discord.User, amount: int):
    """Hak ekleme komutu (Admin)"""

    # Admin kontrolü
    admin_role = interaction.guild.get_role(ADMIN_ROLE_ID)
    if not admin_role or admin_role not in interaction.user.roles:
        embed = discord.Embed(
            title="❌ Yetkisiz",
            description="Bu komutu kullanmak için admin değilsiniz!",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if amount <= 0:
        embed = discord.Embed(
            title="⚠️ Geçersiz",
            description="0'dan büyük bir sayı girin!",
            color=0xff9900
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    new_credits = CreditSystem.add_credits(user.id, amount)

    embed = discord.Embed(
        title="✅ HAK EKLENDİ",
        description=f"**{user.mention}** kullanıcısına hak eklendi",
        color=0x00ff00
    )

    embed.add_field(name="👤 Kullanıcı", value=user.mention, inline=True)
    embed.add_field(name="📦 Eklendi", value=f"{amount} hak", inline=True)
    embed.add_field(name="💰 Yeni Toplam", value=f"{new_credits} hak", inline=True)
    embed.add_field(name="👑 Admin", value=interaction.user.mention, inline=False)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="hak_durum", description="Sorgu hak durumunuzu görüntüleyin")
async def hak_durum(interaction: discord.Interaction):
    """Hak durumu komutu"""

    credits = CreditSystem.get_credits(interaction.user.id)

    embed = discord.Embed(
        title="🎫 SORGU HAK DURUMU",
        description=f"{interaction.user.mention} için hak bilgileri",
        color=0x3498db
    )

    # Hak durumu
    if credits == 0:
        status = "🔴 TÜKENDİ"
        status_desc = "Sorgu yapamazsınız."
    elif credits <= 3:
        status = "🟡 AZALIYOR"
        status_desc = f"Sadece {credits} sorgu hakkınız kaldı."
    else:
        status = "🟢 YETERLİ"
        status_desc = f"{credits} sorgu hakkınız var."

    embed.add_field(
        name="Durum",
        value=f"**Kalan Hak:** `{credits}`\n**Durum:** {status}\n{status_desc}",
        inline=False
    )

    embed.add_field(
        name="📋 NASIL SORGU YAPILIR?",
        value="1. Admin'in açtığı **sorgu panelini** bulun\n"
              "2. **🔍 Sorgu Yap** butonuna tıklayın\n"
              "3. Discord ID'nizi girin\n"
              "4. Sonuç sadece size gösterilir",
        inline=False
    )

    embed.add_field(
        name="ℹ️ BİLGİ",
        value=f"**Discord ID:** `{interaction.user.id}`\n"
              f"**Sorgu Başına:** 1 hak\n"
              f"**Sonuçlar:** Sadece size özel",
        inline=False
    )

    embed.set_footer(text=f"{BOT_NAME}")

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="admin_panel", description="Admin kontrol paneli")
async def admin_panel(interaction: discord.Interaction):
    """Admin paneli"""

    # Admin kontrolü
    admin_role = interaction.guild.get_role(ADMIN_ROLE_ID)
    if not admin_role or admin_role not in interaction.user.roles:
        embed = discord.Embed(
            title="❌ Yetkisiz",
            description="Bu panel için admin değilsiniz!",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    total_users = len(user_credits)
    total_credits = sum(user_credits.values())
    total_sorgular = len(sorgu_gecmisi.get("sorgular", []))

    embed = discord.Embed(
        title="⚙️ ADMIN KONTROL PANELİ",
        description=f"**{BOT_NAME}** - Yönetim Paneli",
        color=0x7289da
    )

    embed.add_field(
        name="📊 İSTATİSTİKLER",
        value=f"**Toplam Kullanıcı:** `{total_users}`\n"
              f"**Toplam Hak:** `{total_credits}`\n"
              f"**Toplam Sorgu:** `{total_sorgular}`\n"
              f"**Ortalama Hak:** `{round(total_credits/max(1, total_users), 1) if total_users > 0 else 0}`",
        inline=False
    )

    embed.add_field(
        name="🔧 SİSTEM KOMUTLARI",
        value="• **`/sorgu_paneli`** - Sorgu paneli aç\n"
              "• **`/hak_ver <kullanıcı> <miktar>`** - Hak ekle\n"
              "• **`/admin_panel`** - Bu panel\n"
              "• **`/hak_durum`** - Hak durumu (herkes)",
        inline=False
    )

    embed.add_field(
        name="📋 SORGU SİSTEMİ",
        value="1. Admin `/sorgu_paneli` açar\n"
              "2. Herkes butona tıklayıp sorgu yapar\n"
              "3. Sonuçlar sadece sorguyu yapana gösterilir\n"
              "4. Her sorgu 1 hak kullanır",
        inline=False
    )

    embed.add_field(
        name="ℹ️ BİLGİ",
        value=f"• Bot: {BOT_NAME}\n• API: {API_URL}\n• Admin Rol ID: `{ADMIN_ROLE_ID}`",
        inline=False
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="sorgu_gecmisi", description="Sorgu geçmişini gör (Admin)")
async def sorgu_gecmisi(interaction: discord.Interaction):
    """Sorgu geçmişi - SADECE ADMIN"""

    # Admin kontrolü
    admin_role = interaction.guild.get_role(ADMIN_ROLE_ID)
    if not admin_role or admin_role not in interaction.user.roles:
        embed = discord.Embed(
            title="❌ Yetkisiz",
            description="Bu komutu kullanmak için admin değilsiniz!",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    total_sorgular = len(sorgu_gecmisi.get("sorgular", []))

    if total_sorgular == 0:
        embed = discord.Embed(
            title="📊 SORGU GEÇMİŞİ",
            description="Henüz hiç sorgu yapılmamış.",
            color=0xff9900
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Son 10 sorguyu al
    son_sorgular = sorgu_gecmisi.get("sorgular", [])[-10:]

    embed = discord.Embed(
        title="📊 SORGU GEÇMİŞİ",
        description=f"**Son {len(son_sorgular)} sorgu** (Toplam: {total_sorgular})",
        color=0x7289da
    )

    for i, sorgu in enumerate(reversed(son_sorgular), 1):
        tarih = datetime.fromisoformat(sorgu["tarih"]).strftime("%d/%m %H:%M")
        embed.add_field(
            name=f"#{total_sorgular - len(son_sorgular) + i} - {tarih}",
            value=f"**Kullanıcı:** <@{sorgu['kullanici_id']}>\n"
                  f"**Sorgulanan:** `{sorgu['sorgulanan_id'][:15]}...`\n"
                  f"**Email:** `{sorgu['email'][:20]}...`\n"
                  f"**IP:** `{sorgu['ip']}`",
            inline=False
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)

# Buton callback'lerini kaydet
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        if interaction.data["custom_id"] == "sorgu_yap":
            # View'ı yeniden oluştur
            view = SorguView(interaction.message.id)
            await interaction.response.send_modal(SorguModal(interaction.message.id))

    await bot.process_application_commands(interaction)

# BOTU BAŞLAT
print(f"🚀 {BOT_NAME} başlatılıyor...")
print(f"🌐 API: {API_URL}")
print("📊 SİSTEM: Admin Panel + Kullanıcı Sorgu")
print("1. Admin /sorgu_paneli açar")
print("2. Herkes butona tıklayıp sorgu yapar")
print("3. Sonuçlar sadece sorguyu yapana gösterilir")
try:
    bot.run(TOKEN)
except Exception as e:
    print(f"❌ Hata: {e}")
    # ================= WEB PANEL =================
    from flask import Flask, request, render_template_string
    from threading import Thread

    app = Flask(__name__)

    HTML = """
    <!doctype html>
    <html>
    <head>
      <title>Vahset Intelligence Panel</title>
      <style>
        body { background:#0f0f0f; color:#eee; font-family:Arial; }
        .box { max-width:500px; margin:auto; margin-top:50px; padding:20px; border:1px solid #333; }
        input, button { width:100%; padding:10px; margin-top:10px; background:#111; color:#fff; border:1px solid #444; }
        button { cursor:pointer; }
        h2 { color:#8B0000; text-align:center; }
      </style>
    </head>
    <body>
      <div class="box">
        <h2>VAHSET INTELLIGENCE</h2>
        <p><b>Bot Durumu:</b> {{ status }}</p>
        <p><b>Toplam Kullanıcı:</b> {{ total_users }}</p>
        <p><b>Toplam Hak:</b> {{ total_credits }}</p>

        <hr>

        <form method="post">
          <label>Discord ID</label>
          <input name="user_id" placeholder="801174548883832832">
          <button type="submit">Hak Sorgula</button>
        </form>

        {% if result %}
          <p><b>Sonuç:</b> {{ result }}</p>
        {% endif %}
      </div>
    </body>
    </html>
    """

    @app.route("/", methods=["GET", "POST"])
    def panel():
        result = None
        if request.method == "POST":
            uid = request.form.get("user_id", "").strip()
            if uid.isdigit():
                credits = user_credits.get(uid)
                if credits is None:
                    result = "Kullanıcı bulunamadı"
                else:
                    result = f"Kalan Hak: {credits}"
            else:
                result = "Geçersiz ID"

        return render_template_string(
            HTML,
            status="🟢 Online" if bot.is_ready() else "🔴 Offline",
            total_users=len(user_credits),
            total_credits=sum(user_credits.values()),
            result=result
        )

    def run_web():
        app.run(host="0.0.0.0", port=8080)

    def keep_alive():
        Thread(target=run_web).start()

    keep_alive()
    # ================= WEB PANEL =================
