from enum import Enum

class WSEventType(str, Enum):
    NEW_MESSAGE = "new_message"
    DELETE_MESSAGE = "delete_message"
    MESSAGE_READ = "message_read"
    MESSAGE_REACTION = "message_reaction"
    NEW_CHAT = "new_chat"
    CHAT_UPDATED = "chat_updated"
    CHAT_DELETED = "chat_deleted"
    USER_STATUS = "user_status"
    ONLINE_LIST = "online_list"
    USER_UPDATED = "user_updated"
    TYPING = "typing"
    USER_STATUS_UPDATE = "user_status_update"
