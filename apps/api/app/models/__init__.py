"""Database models. Import all here so Base.metadata sees every table."""
from app.models.asset import Asset, AssetAnalysis
from app.models.assistant import Conversation, Message, ProposedAction
from app.models.earnings import (
    BusinessRecord,
    IncomeSource,
    SavingsVehicle,
    VehicleFlow,
)
from app.models.finance import Account, Transaction
from app.models.goal import Goal, GoalContribution
from app.models.inventory import InventoryCategory, InventoryItem, QuantityEvent
from app.models.notifications import NotificationPreference
from app.models.shopping import PurchaseRecord, ShoppingItem, ShoppingList
from app.models.student import (
    FeeObligation,
    FeePayment,
    FoodBudget,
    HostelOption,
)
from app.models.tasks import Task
from app.models.user import User
from app.models.valuation import NetWorthSnapshot

__all__ = [
    "User",
    "Account",
    "Transaction",
    "InventoryCategory",
    "InventoryItem",
    "QuantityEvent",
    "Asset",
    "AssetAnalysis",
    "Goal",
    "GoalContribution",
    "ShoppingList",
    "ShoppingItem",
    "PurchaseRecord",
    "IncomeSource",
    "BusinessRecord",
    "SavingsVehicle",
    "VehicleFlow",
    "Task",
    "FeeObligation",
    "FeePayment",
    "HostelOption",
    "FoodBudget",
    "NotificationPreference",
    "Conversation",
    "Message",
    "ProposedAction",
    "NetWorthSnapshot",
]
