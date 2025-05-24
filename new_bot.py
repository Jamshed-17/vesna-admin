import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from checking_message import main_check_add
from configg import BOT_TOKEN, GROUP_ID
from temp_word import abusive_language
import re
from urllib.parse import urlparse
import time

TOKEN = BOT_TOKEN

SPAM_PATTERNS = [
    r'\d{3,}р|\d{3,}руб|\d{3,}p|\d{3,}₽',
    r'заработок|зараб[о0]тк[аa]|з[аa]рплат[аa]',
    r'подработк[аa]|работа|вакансия',
    r'[з3]а\s*\d+\s*минут',
    r'http[s]?://\S+',
    r'[\w-]+\.(com|ru|net|org|рф|su|xyz)',
    r'\[id\d+\|.+\]',
    r'@\w{5,}|@[\w-]+\.[\w-]+',
    r'[8|+7][\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}',
]

OBSCENE_PATTERNS = abusive_language

class SmartModerator:
    def __init__(self):
        self.vk_session = vk_api.VkApi(token=TOKEN)
        self.vk = self.vk_session.get_api()
        self.longpoll = VkBotLongPoll(self.vk_session, GROUP_ID)

        self.spam_regex = [re.compile(p, re.IGNORECASE) for p in SPAM_PATTERNS]
        self.obscene_regex = [re.compile(p, re.IGNORECASE) for p in OBSCENE_PATTERNS]

        self.user_warnings = {}  # {user_id: count}
        self.deleted_messages = {}  # {peer_id: {'msg_id': ..., 'text': ..., 'user_id': ..., 'reason': ...}}

    def delete_message(self, msg_id, peer_id, user_id, text, reason):
        try:
            self.vk.messages.delete(
                peer_id=peer_id,
                delete_for_all=1,
                cmids=msg_id,
                group_id=GROUP_ID
            )

            # Сохраняем последнее удаление
            self.deleted_messages[peer_id] = {
                'msg_id': msg_id,
                'text': text,
                'user_id': user_id,
                'reason': reason
            }

            # Увеличиваем предупреждение
            self.user_warnings[user_id] = self.user_warnings.get(user_id, 0) + 1
            warning = self.user_warnings[user_id]

            # Отправка уведомления
            self.vk.messages.send(
                peer_id=peer_id,
                message=f"⚠️ Сообщение удалено из-за нарушения правил сообщества, предупреждение {warning}/3",
                random_id=0
            )

            # Бан при 3 предупреждениях
            if warning >= 3:
                self.vk.messages.send(
                    peer_id=peer_id,
                    message=f"🚫 [id{user_id}|Пользователь] заблокирован за 3 нарушения.",
                    random_id=0
                )
                # Здесь можно реализовать бан через chat_kick, если нужно
        except Exception:
            pass

    def restore_message(self, peer_id):
        data = self.deleted_messages.get(peer_id)
        if not data:
            return

        user_id = data['user_id']
        self.user_warnings[user_id] = max(0, self.user_warnings.get(user_id, 1) - 1)

        try:
            self.vk.messages.send(
                peer_id=peer_id,
                message=f"↩️ Отмена: восстановлено сообщение от [id{user_id}|пользователя]:\n\n{data['text']}",
                random_id=0
            )
            del self.deleted_messages[peer_id]
        except Exception:
            pass

    def is_spam(self, text):
        has_money = re.search(r'\d{3,}\s*(р|руб|p|₽)', text, re.IGNORECASE)
        keywords = re.search(r'заработок|зараб[о0]тк[аa]|з[аa]рплат[аa]|подработк[аa]|работа|вакансия', text, re.IGNORECASE)

        urls = re.findall(r'http[s]?://[^\s]+', text)
        suspicious_domains = any(
            urlparse(url).netloc.endswith(('.com', '.ru', '.net')) 
            for url in urls
        )

        return bool(has_money or keywords or suspicious_domains)

    def check_message(self, text):
        if any(p.search(text) for p in self.obscene_regex):
            return "нецензурная лексика"
        if self.is_spam(text):
            return "спам/реклама"
        if re.search(r'(.+?)(\1{3,})', text):
            return "флуд"
        return None

    def run(self):
        for event in self.longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW and event.from_chat:
                msg = event.object.message
                text = msg.get('text', '').strip()
                msg_id = msg['conversation_message_id']
                peer_id = msg['peer_id']
                user_id = msg['from_id']

                if not text:
                    continue

                if text.lower() == "/отмена":
                    self.restore_message(peer_id)
                    continue

                reason = self.check_message(text)
                if reason:
                    self.delete_message(msg_id, peer_id, user_id, text, reason)

if __name__ == "__main__":
    bot = SmartModerator()
    bot.run()
