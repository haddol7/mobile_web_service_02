"""Offline deployment scope checks; these tests do not load authentication."""
import unittest
from deploy_security_patch import changed_files


class SecurityPatchScopeTests(unittest.TestCase):
    def manifests(self, *paths):
        return {"files":[{"path":path,"sha256":"old"} for path in paths]}

    def test_only_reviewed_security_files_can_change(self):
        old = self.manifests("blog/history_llm.py", "blog/models.py")
        new = self.manifests("blog/history_llm.py", "blog/models.py", "blog/request_limits.py")
        new["files"][0]["sha256"] = "new"
        _, _, changed = changed_files(old,new)
        self.assertEqual(changed,{"blog/history_llm.py","blog/request_limits.py"})

    def test_models_dependencies_migrations_and_unapproved_additions_are_rejected(self):
        for path in ("blog/models.py","requirements.txt","blog/migrations/new.py","blog/unapproved.py"):
            with self.subTest(path=path), self.assertRaises(AssertionError):
                changed_files(self.manifests(path),{"files":[{"path":path,"sha256":"new"}]})

    def test_existing_file_deletion_is_rejected(self):
        with self.assertRaises(AssertionError):
            changed_files(self.manifests("blog/history_llm.py"), self.manifests("blog/request_limits.py"))


if __name__ == "__main__":
    unittest.main()
