"""Build the actual Tk widgets with synthetic messages; no network or database."""

import tkinter as tk
import unittest
from unittest.mock import patch

from client.client import MessengerWindow
from client.moderation import ModerationWindow
from client.profile import ProfileWindow
from client.profile_view import PublicProfileWindow
from common.config import load_settings


class ModerationWidgetTests(unittest.TestCase):
    def test_admin_review_selection_and_restoration_controls(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = MessengerWindow(root, load_settings())
            app.current_user = {"id": 1, "username": "admin_test", "role": "admin"}
            app.token = "synthetic-session"
            with patch.object(app, "_run_async"):
                app.show_dashboard()
            with patch.object(ModerationWindow, "request"):
                review = ModerationWindow(root, app.api, app.token)
                review.window.withdraw()
                row = dict(id=1, sender_username="alice", recipient_username="bob", created_at="2026-09-28",
                           body="多行原文\n第二行", is_blocked=False)
                review.loaded({"messages": [row], "has_more": False})
                review.tree.selection_set("1")
                review.show_detail()
                self.assertIn("第二行", review.detail.get("1.0", "end"))
                self.assertEqual(str(review.block_button["state"]), "normal")
                self.assertEqual(str(review.restore_button["state"]), "disabled")
                row.update(is_blocked=True, reason="违规原因", moderator_username="admin_test", moderated_at="now")
                review.loaded({"messages": [row], "has_more": False})
                self.assertIn("违规原因", review.detail.get("1.0", "end"))
                self.assertEqual(str(review.block_button["state"]), "disabled")
                self.assertEqual(str(review.restore_button["state"]), "normal")
                review.loaded({"messages": [], "has_more": False})
                self.assertEqual(str(review.restore_button["state"]), "disabled")
                review.close()
        finally:
            root.destroy()

    def test_personal_center_keeps_gender_entry_open_for_self_description(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = MessengerWindow(root, load_settings())
            app.current_user = {"id": 1, "username": "profile_test", "role": "user"}
            app.token = "synthetic-session"
            with patch.object(ProfileWindow, "request"):
                profile = ProfileWindow(root, app.api, app.token, lambda _user: None)
                profile.window.withdraw()
                profile.loaded({"user": {
                    "id": 1, "username": "profile_test", "role": "user", "is_active": True,
                    "gender_identity": "性别酷儿", "job_title": "设计师", "bio": "测试简介", "avatar": None,
                }})
                self.assertEqual(str(profile.gender["state"]), "normal")
                profile.gender.set("我的自定义性别认同")
                self.assertEqual(profile.gender.get(), "我的自定义性别认同")
                self.assertIn("个人中心", profile.window.title())
                self.assertIn("保存个人资料", str(profile.save_button["text"]))
                profile.close()
        finally:
            root.destroy()

    def test_contact_list_groups_users_and_administrators_by_job_title(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = MessengerWindow(root, load_settings())
            app.current_user = {"id": 1, "username": "self_user", "role": "user"}
            app.token = "synthetic-session"
            with patch.object(app, "_run_async"):
                app.show_dashboard()
            app._show_contacts({"users": [
                {"id": 2, "username": "admin_design", "role": "admin", "is_active": True, "job_title": "设计师"},
                {"id": 3, "username": "user_design", "role": "user", "is_active": True, "job_title": "设计师"},
                {"id": 4, "username": "user_unknown", "role": "user", "is_active": True, "job_title": ""},
            ]})
            groups = app.contact_tree.get_children()
            self.assertEqual([app.contact_tree.item(group, "text") for group in groups], ["职位 · 设计师", "职位 · 未填写职位"])
            design_contacts = app.contact_tree.get_children(groups[0])
            self.assertEqual(app.contact_tree.item(design_contacts[0], "values"), ("管理员",))
            self.assertEqual(app.contact_tree.item(design_contacts[1], "values"), ("用户",))
            with patch.object(app, "refresh_conversation") as refresh:
                app.contact_tree.selection_set(design_contacts[0])
                app.select_contact()
                refresh.assert_called_once()
                self.assertEqual(app.selected_contact["username"], "admin_design")
        finally:
            root.destroy()

    def test_public_profile_keeps_the_job_label_with_the_value(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = MessengerWindow(root, load_settings())
            with patch.object(PublicProfileWindow, "request"):
                profile = PublicProfileWindow(root, app.api, "synthetic-session", 2)
                profile.window.withdraw()
                profile.loaded({
                    "id": 2, "username": "designer", "role": "user", "gender_identity": "非二元性别",
                    "job_title": "产品设计师", "bio": "简介", "avatar": None,
                })
                self.assertEqual(profile.job_title.get(), "职位：产品设计师")
                profile.close()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
