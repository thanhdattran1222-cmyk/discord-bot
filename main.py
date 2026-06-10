import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import os
import json
from datetime import datetime, timezone
from dateutil import parser

# --- 1. HỆ THỐNG CẤU HÌNH & DỮ LIỆU ---
TOKEN = ""
FILE_DB = "blacklist_data.json"
# Cấu hình các kênh quét lịch sử (Hỗ trợ quét không giới hạn tin nhắn)
CH_BLACKLIST_USER_IDS = [1257359862594277376, 1462789197189615677]

def load_data():
    if os.path.exists(FILE_DB):
        try:
            with open(FILE_DB, "r", encoding="utf-8") as f: return json.load(f)
        except: return []
    return []

DANH_SACH_DEN = load_data()

def save_data():
    with open(FILE_DB, "w", encoding="utf-8") as f:
        json.dump(DANH_SACH_DEN, f, indent=4)

# --- 2. KHỞI TẠO BOT ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="?", intents=intents, heartbeat_timeout=150.0)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"Kho đã nạp {len(DANH_SACH_DEN)} mục tiêu nhóm.")

    async def on_ready(self):
        print(f'✅ Bot đã sẵn sàng: {self.user.name}')
    
bot = MyBot()

# --- 3. TIỆN ÍCH TRUY XUẤT ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound): return
    raise error

async def fetch_roblox(session, url, method="GET", data=None):
    try:
        if method == "POST":
            async with session.post(url, json=data) as response: return await response.json()
        async with session.get(url) as response: return await response.json()
    except: return None


# --- 🌟 HỆ THỐNG PHÂN TRANG CHI TIẾT (DÙNG CHO /CHECKACCOUNT) 🌟 ---
class MultiAccountView(discord.ui.View):
    def __init__(self, embeds, group_texts):
        super().__init__(timeout=600)
        self.embeds = embeds
        self.group_texts = group_texts
        self.current_page = 0
        self.update_buttons()

    def update_buttons(self):
        self.prev_page.disabled = self.current_page == 0
        self.next_page.disabled = self.current_page == len(self.embeds) - 1

    @discord.ui.button(label="Trước", style=discord.ButtonStyle.blurple, emoji="⬅️", custom_id="prev_btn")
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="Danh Sách Nhóm", style=discord.ButtonStyle.secondary, emoji="📋", custom_id="group_btn")
    async def show_groups(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_text = self.group_texts[self.current_page]
        await interaction.response.send_message(content=current_text[:2000], ephemeral=True)

    @discord.ui.button(label="Sau", style=discord.ButtonStyle.blurple, emoji="➡️", custom_id="next_btn")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)


# --- 🌟 HỆ THỐNG PHÂN TRANG TỔNG HỢP (DÙNG CHO /CHECKALL) 🌟 ---
class CheckAllView(discord.ui.View):
    def __init__(self, embeds):
        super().__init__(timeout=600)
        self.embeds = embeds
        self.current_page = 0
        self.update_buttons()

    def update_buttons(self):
        self.prev_page.disabled = self.current_page == 0
        self.next_page.disabled = self.current_page == len(self.embeds) - 1

    @discord.ui.button(label="Trước", style=discord.ButtonStyle.blurple, emoji="⬅️", custom_id="all_prev_btn")
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="Sau", style=discord.ButtonStyle.blurple, emoji="➡️", custom_id="all_next_btn")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)


# --- 4. HỆ THỐNG LỆNH CHÍNH ---

# LỆNH 1: TRINH SÁT CHI TIẾT TỪNG NGƯỜI
@bot.tree.command(name="checkaccount", description="Kiểm tra hồ sơ một hoặc nhiều đối tượng (xem chi tiết từng người)")
@app_commands.describe(usernames="Nhập các tên cách nhau bằng dấu phẩy (Ví dụ: user1, user2, user3)")
async def checkaccount(interaction: discord.Interaction, usernames: str):
    await interaction.response.defer()
    
    list_names = [name.strip() for name in usernames.split(",") if name.strip()]
    if not list_names:
        return await interaction.followup.send("❌ Vui lòng nhập ít nhất một username!")

    all_embeds = []
    all_group_texts = []

    async with aiohttp.ClientSession() as session:
        u_data = await fetch_roblox(session, "https://users.roblox.com/v1/usernames/users", "POST", {"usernames": list_names, "excludeBannedUsers": True})
        
        if not u_data or not u_data.get("data"):
            return await interaction.followup.send("❌ Không tìm thấy đối tượng nào!")

        found_users = u_data["data"]
        
        for index, user_info in enumerate(found_users):
            u_id = user_info["id"]
            u_name = user_info["name"]
            d_name = user_info["displayName"]
            profile_url = f"https://www.roblox.com/users/{u_id}/profile"
            
            tasks = [
                fetch_roblox(session, f"https://users.roblox.com/v1/users/{u_id}"),
                fetch_roblox(session, f"https://friends.roblox.com/v1/users/{u_id}/friends/count"),
                fetch_roblox(session, f"https://groups.roblox.com/v2/users/{u_id}/groups/roles"),
                fetch_roblox(session, f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={u_id}&size=420x420&format=Png")
            ]
            u_details, friends_data, g_data, thumb_data = await asyncio.gather(*tasks)
            
            friends = friends_data.get("count", 0) if friends_data else 0
            all_groups = g_data.get("data", []) if g_data else []
            
            try:
                created = parser.isoparse(u_details["created"]).replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - created).days
                sc = u_details.get("isVieweeSafeChat")
            except:
                created = datetime.now(timezone.utc)
                age = 0
                sc = False

            # Quét lịch sử kênh chat không giới hạn
            is_user_blacklisted = False
            found_in_channels = []
            for channel_id in CH_BLACKLIST_USER_IDS:
                channel = bot.get_channel(channel_id)
                if channel:
                    async for message in channel.history(limit=None):
                        content_to_check = message.content.lower()
                        if message.embeds:
                            for em in message.embeds:
                                if em.description: content_to_check += " " + em.description.lower()
                                for f in em.fields: content_to_check += " " + f.name.lower() + " " + f.value.lower()
                        
                        if u_name.lower() in content_to_check:
                            is_user_blacklisted = True
                            found_in_channels.append(channel.name)
                            break

            warns = []
            if sc: warns.append(f"⚠️ **Safe Chat:** Trạng thái đang BẬT")
            if age < 100: warns.append(f"⚠️ Tuổi acc thấp: {age}/100 ngày")
            if friends < 50: warns.append(f"⚠️ Ít bạn bè: {friends}/50 bạn bè")
            if len(all_groups) < 5: warns.append(f"⚠️ Ít nhóm: {len(all_groups)}/5 nhóm")
            if is_user_blacklisted:
                warns.append(f"🚨 **Bị Blacklist:** Tại kênh #{', '.join(found_in_channels)}")
            
            bad_found = []
            for g in all_groups:
                if g['group']['id'] in DANH_SACH_DEN:
                    bad_found.append(f"❌ **{g['group']['name']}** `{g['role']['name']}`")

            is_fail = (len(warns) > 0 or len(bad_found) > 0 or is_user_blacklisted)
            
            embed = discord.Embed(
                title="HỆ THÔNG KIỂM TRA THÔNG TIN KSQS",
                description=f"Hồ sơ quân nhân.\nDanh tính đối tượng: **[{u_name}]({profile_url})**",
                color=0xe74c3c if is_fail else 0x2ecc71,
                timestamp=datetime.now()
            )
            if interaction.guild and interaction.guild.icon:
                embed.set_author(name="BỘ TƯ LỆNH KIỂM SOÁT QUÂN SỰ", icon_url=interaction.guild.icon.url)
            else:
                embed.set_author(name="BỘ TƯ LỆNH KIỂM SOÁT QUÂN SỰ")
            
            try:
                embed.set_thumbnail(url=thumb_data["data"][0]["imageUrl"])
            except: pass
            
            embed.add_field(
                name="👤 THÔNG TIN ĐỐI TƯỢNG",
                value=(
                    f"• **Display Name:** `{d_name}`\n"
                    f"• **User Name:** `{u_name}`\n"
                    f"• **Roblox ID:** `{u_id}`"
                ),
                inline=True
            )
            
            embed.add_field(
                name="📊 THÔNG TIN CHỈ SỐ",
                value=(
                    f"• **Tuổi Acc:** `{age}` ngày\n"
                    f"• **Bạn bè:** `{friends}` người\n"
                    f"• **Tổng số nhóm:** `{len(all_groups)}` nhóm"
                ),
                inline=True
            )

            warn_content = "\n".join([f"• {w}" for w in warns]) if warns else "Thông tin đủ điều kiện ✅"
            embed.add_field(
                name="⚠️ĐÁNH GIÁ ĐIỀU KIỆN⚠️", 
                value=f"""```md\n{warn_content}\n```""", 
                inline=False
            )

            black_group_content = "\n".join(bad_found) if bad_found else "✅ Không phát hiện tham gia tổ chức bất hợp pháp."
            embed.add_field(name="🚫 KIỂM TRA GROUP BLACKLIST 🚫", value=black_group_content, inline=False)

            status_text = "❌ KHÔNG ĐỦ ĐIỀU KIỆN" if is_fail else "✅ TÀI KHOẢN ĐỦ ĐIỀU KIỆN"
            embed.add_field(name="📢 KẾT LUẬN CUỐI CÙNG", value=f"**{status_text}**", inline=False)
            
            embed.set_footer(
                text=f"BTL KSQS • Dùng bởi: {interaction.user.display_name} • Trang: {index + 1}/{len(found_users)} • Code by canhdeptai"
            )
            
            all_embeds.append(embed)
            
            group_list_text = f"📋 **DANH SÁCH NHÓM TOÀN BỘ CỦA {u_name.upper()}:**\n\n" + "\n".join([f"• {g['group']['name']} (ID: {g['group']['id']})" for g in all_groups])
            all_group_texts.append(group_list_text)

    not_found_names = [name for name in list_names if name.lower() not in [u["name"].lower() for u in found_users]]
    
    if all_embeds:
        view = MultiAccountView(all_embeds, all_group_texts)
        msg_content = f"⚠️ **Hệ thống bỏ qua do sai tên:** `{', '.join(not_found_names)}`" if not_found_names else None
        await interaction.followup.send(content=msg_content, embed=all_embeds[0], view=view)
    else:
        await interaction.followup.send("❌ Không có dữ liệu hồ sơ nào được trích xuất thành công.")


# LỆNH 2: TỔNG HỢP VÀ PHÂN TRANG DANH SÁCH
@bot.tree.command(name="checkall", description="Kiểm tra diện rộng (tổng hợp danh sách đạt/không đạt kèm lý do vi phạm)")
@app_commands.describe(usernames="Nhập các tên cách nhau bằng dấu phẩy (Ví dụ: user1, user2, user3)")
async def checkall(interaction: discord.Interaction, usernames: str):
    await interaction.response.defer()
    list_names = [n.strip() for n in usernames.split(",") if n.strip()]
    if not list_names: return await interaction.followup.send("❌ Nhập tên đi!")
    
    async with aiohttp.ClientSession() as session:
        u_data = await fetch_roblox(session, "https://users.roblox.com/v1/usernames/users", "POST", {"usernames": list_names, "excludeBannedUsers": True})
        if not u_data or "data" not in u_data: return await interaction.followup.send("❌ Roblox không trả về dữ liệu!")
        
        found_users = u_data["data"]
        all_user_summaries = []
        
        for user_info in found_users:
            u_id = user_info["id"]
            u_name = user_info["name"]
            profile_url = f"https://www.roblox.com/users/{u_id}/profile"
            
            tasks = [
                fetch_roblox(session, f"https://users.roblox.com/v1/users/{u_id}"),
                fetch_roblox(session, f"https://friends.roblox.com/v1/users/{u_id}/friends/count"),
                fetch_roblox(session, f"https://groups.roblox.com/v2/users/{u_id}/groups/roles")
            ]
            u_details, friends_data, g_data = await asyncio.gather(*tasks)
            
            friends = friends_data.get("count", 0) if friends_data else 0
            all_groups = g_data.get("data", []) if g_data else []
            
            try:
                created = parser.isoparse(u_details["created"]).replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - created).days
                sc = u_details.get("isVieweeSafeChat") if u_details else False
            except:
                created = datetime.now(timezone.utc)
                age = 0
                sc = False

            # Quét lịch sử kênh chat không giới hạn
            is_user_blacklisted = False
            found_in_channels = []
            for channel_id in CH_BLACKLIST_USER_IDS:
                channel = bot.get_channel(channel_id)
                if channel:
                    async for message in channel.history(limit=1000):
                        content_to_check = message.content.lower()
                        if message.embeds:
                            for em in message.embeds:
                                if em.description: content_to_check += " " + em.description.lower()
                                for f in em.fields: content_to_check += " " + f.name.lower() + " " + f.value.lower()
                        
                        if u_name.lower() in content_to_check:
                            is_user_blacklisted = True
                            found_in_channels.append(channel.name)
                            break

            # Phân tích các điểm không đủ điều kiện
            ineligible_reasons = []
            if sc:
                ineligible_reasons.append("Safe Chat: BẬT")
            if age < 100:
                ineligible_reasons.append(f"**Tuổi acc thấp** ({age}/100 ngày)")
            if friends < 50:
                ineligible_reasons.append(f"**Ít bạn bè** ({friends}/50 người)")
            if len(all_groups) < 5:
                ineligible_reasons.append(f"**Ít nhóm** ({len(all_groups)}/5 nhóm)")
            if is_user_blacklisted:
                ineligible_reasons.append(f"**Blacklist tại kênh** #{', '.join(found_in_channels)}")

            # Kiểm tra Group Blacklist
            bad_groups = []
            for g in all_groups:
                if g['group']['id'] in DANH_SACH_DEN:
                    bad_groups.append(f"❌ **{g['group']['name']}** `{g['role']['name']}`")

            if bad_groups:
                ineligible_reasons.append(f"Group Blacklist: {', '.join(bad_groups)}")

            is_fail = len(ineligible_reasons) > 0
            
            # Đóng gói thông tin hiển thị của đối tượng
            status_emoji = "🔴" if is_fail else "🟢"
            status_text = "Không đủ điều kiện" if is_fail else "Đủ điều kiện"
            
            user_line = f"{status_emoji} **[{u_name}]({profile_url})** - **{status_text}**"
            if is_fail:
                reasons_bullet = "\n".join([f"    └ *{reason}*" for reason in ineligible_reasons])
                user_line += f"\n{reasons_bullet}"
                
            all_user_summaries.append((user_line, is_fail))

    # Chia danh sách đối tượng thành các trang (Mỗi trang tối đa 5 đối tượng)
    chunk_size = 10
    summary_chunks = [all_user_summaries[i:i + chunk_size] for i in range(0, len(all_user_summaries), chunk_size)]
    
    all_embeds = []
    for index, chunk in enumerate(summary_chunks):
        page_description = "\n\n".join([item[0] for item in chunk])
        page_has_fail = any(item[1] for item in chunk)
        
        embed = discord.Embed(
            title="🛡️ BẢN TỔNG HỢP DANH SÁCH KIỂM TRA",
            description=page_description,
            color=0xe74c3c if page_has_fail else 0x2ecc71,
            timestamp=datetime.now()
        )
        if interaction.guild and interaction.guild.icon:
            embed.set_author(name="BỘ TƯ LỆNH KIỂM SOÁT QUÂN SỰ", icon_url=interaction.guild.icon.url)
        else:
            embed.set_author(name="BỘ TƯ LỆNH KIỂM SOÁT QUÂN SỰ")
            
        embed.set_footer(
            text=f"BTL KSQS • Dùng bởi: {interaction.user.display_name} • Trang {index + 1}/{len(summary_chunks)} • Code by canhdeptai"
        )
        all_embeds.append(embed)

    not_found_names = [name for name in list_names if name.lower() not in [u["name"].lower() for u in found_users]]

    if all_embeds:
        view = CheckAllView(all_embeds)
        msg_content = f"⚠️ **Hệ thống bỏ qua do sai tên:** `{', '.join(not_found_names)}`" if not_found_names else None
        await interaction.followup.send(content=msg_content, embed=all_embeds[0], view=view)
    else:
        await interaction.followup.send("❌ Không thể kiểm tra thông tin diện rộng.")


# --- CÁC LỆNH QUẢN LÝ GROUP DISCORD (GIỮ NGUYÊN) ---
@bot.tree.command(name="blacklist_add", description="Thêm ID nhóm vào group blacklist")
async def blacklist_add(interaction: discord.Interaction, ids: str):
    if not interaction.user.guild_permissions.administrator: return
    global DANH_SACH_DEN
    raw_ids = ids.replace(" ", "").split(",")
    added = 0
    for r_id in raw_ids:
        if r_id.isdigit() and int(r_id) not in DANH_SACH_DEN:
            DANH_SACH_DEN.append(int(r_id)); added += 1
    save_data()
    await interaction.response.send_message(f"### ✅ Đã lưu `{added}` ID. Tổng kho: `{len(DANH_SACH_DEN)}`.")

@bot.tree.command(name="blacklist_remove", description="Gỡ bỏ ID khỏi kho vĩnh viễn")
async def blacklist_remove(interaction: discord.Interaction, ids: str):
    if not interaction.user.guild_permissions.administrator: return
    global DANH_SACH_DEN
    raw_ids = ids.replace(" ", "").split(",")
    removed = 0
    for r_id in raw_ids:
        if r_id.isdigit() and int(r_id) in DANH_SACH_DEN:
            DANH_SACH_DEN.remove(int(r_id)); removed += 1
    save_data()
    await interaction.response.send_message(f"### ✅ Đã xóa thành công `{removed}` ID GROUP.")

@bot.tree.command(name="check_blacklist", description="Xem danh sách group blacklist hiện có")
async def check_blacklist(interaction: discord.Interaction):
    if not DANH_SACH_DEN: 
        return await interaction.response.send_message("📝 Kho trống.")
    await interaction.response.defer()
    async with aiohttp.ClientSession() as session:
        results = []
        for g_id in DANH_SACH_DEN:
            res = await fetch_roblox(session, f"https://groups.roblox.com/v1/groups/{g_id}")
            name = res.get('name', 'N/A')
            results.append(f"🛑 **{name}** (`{g_id}`)")
        
        full_message = "\n".join(results)
        if len(full_message) > 1900:
            current_msg = ""
            for line in results:
                if len(current_msg) + len(line) > 1900:
                    await interaction.channel.send(current_msg)
                    current_msg = line + "\n"
                else: current_msg += line + "\n"
            if current_msg: await interaction.followup.send(current_msg)
        else: await interaction.followup.send(full_message)

# --- VIEW DÀNH RIÊNG CHO CHECK DISCORD ---
class DiscordCheckView(discord.ui.View):
    def __init__(self, embeds):
        super().__init__(timeout=200)
        self.embeds = embeds
        self.current_page = 0
        self.update_buttons()

    def update_buttons(self):
        self.prev_page.disabled = self.current_page == 0
        self.next_page.disabled = self.current_page == len(self.embeds) - 1

    @discord.ui.button(label="Trước", style=discord.ButtonStyle.blurple, emoji="⬅️")
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="Sau", style=discord.ButtonStyle.blurple, emoji="➡️")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

# --- LỆNH CHECKDISCORD MỚI ---
@bot.tree.command(name="checkdiscord", description="Kiểm tra thông tin Discord (hỗ trợ nhiều ID cách nhau bằng dấu phẩy)")
@app_commands.describe(user_ids="Nhập ID, ví dụ: 12345, 67890")
async def checkdiscord(interaction: discord.Interaction, user_ids: str):
    await interaction.response.defer()
    id_list = [i.strip() for i in user_ids.split(",") if i.strip()]
    all_embeds = []

    for uid in id_list:
        try:
            user = await bot.fetch_user(int(uid))
        except:
            continue

        created_at = user.created_at
        age_days = (datetime.now(timezone.utc) - created_at).days
        
        # Quét blacklist
        is_blacklisted = False
        found_in = []
        for channel_id in CH_BLACKLIST_USER_IDS:
            channel = bot.get_channel(channel_id)
            if channel:
                async for message in channel.history(limit=None):
                    if str(user.id) in message.content:
                        is_blacklisted = True
                        found_in.append(channel.name)
                        break

        # Tạo Embed
        color = 0xe74c3c if (age_days < 60 or is_blacklisted) else 0x2ecc71
        embed = discord.Embed(title="🛡️ HỒ SƠ DISCORD", color=color, timestamp=datetime.now())
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="👤 THÔNG TIN", value=f"• **Username:** {user.name}\n• **ID:** `{user.id}`\n• **Ngày tạo:** {created_at.strftime('%d/%m/%Y')}", inline=False)
        embed.add_field(name="📊 THỐNG KÊ", value=f"• **Tuổi acc:** {age_days} ngày", inline=False)
        
        reasons = []
        if age_days < 60: reasons.append(f"• **Tuổi acc thấp:** ({age_days} ngày)")
        if is_blacklisted: reasons.append(f"• **Bị Blacklist** tại: #{', '.join(found_in)}")
        
        embed.add_field(name="📢 KẾT LUẬN", value="\n".join(reasons) if reasons else "Tài khoản ok ✅", inline=False)
        all_embeds.append(embed)
        embed.set_footer(
                text=f"BTL KSQS • Dùng bởi: {interaction.user.display_name} • Trang: {len(all_embeds)}/{len(id_list)} • Code by canhdeptai"
            )
    if not all_embeds:
        await interaction.followup.send("❌ Không tìm thấy thông tin.")
    else:
        view = DiscordCheckView(all_embeds)
        await interaction.followup.send(embed=all_embeds[0], view=view)

if TOKEN: bot.run(TOKEN)
