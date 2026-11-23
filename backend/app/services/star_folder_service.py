"""
app/services/star_folder_service.py
收藏分组（文件夹）业务层：命名校验、重名冲突与归属调整。
"""
import logging

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.repositories.star_folder_repo import star_folder_repo

logger = logging.getLogger(__name__)

MAX_NAME_LENGTH = 40


class StarFolderService:

    @staticmethod
    def _normalize_name(raw: str) -> str:
        """折叠空白并校验长度；空名/纯空白视为非法。"""
        name = " ".join((raw or "").split())
        if not name:
            raise BadRequestError("文件夹名称不能为空")
        if len(name) > MAX_NAME_LENGTH:
            raise BadRequestError(f"文件夹名称不能超过 {MAX_NAME_LENGTH} 个字符")
        return name

    def list_folders(self) -> dict:
        total, uncategorized = star_folder_repo.starred_counts()
        return {
            "folders": star_folder_repo.list_with_counts(),
            "total_starred": total,
            "uncategorized_count": uncategorized,
        }

    def create_folder(self, name: str) -> dict:
        normalized = self._normalize_name(name)
        existing = star_folder_repo.get_by_name(normalized)
        if existing:
            raise ConflictError("已存在同名文件夹")
        return star_folder_repo.create(normalized)

    def rename_folder(self, folder_id: str, name: str) -> dict:
        folder = star_folder_repo.get(folder_id)
        if not folder:
            raise NotFoundError("文件夹不存在")
        normalized = self._normalize_name(name)
        existing = star_folder_repo.get_by_name(normalized)
        if existing and existing["id"] != folder_id:
            raise ConflictError("已存在同名文件夹")
        updated = star_folder_repo.rename(folder_id, normalized)
        if not updated:
            raise NotFoundError("文件夹不存在")
        return updated

    def delete_folder(self, folder_id: str) -> bool:
        if not star_folder_repo.get(folder_id):
            raise NotFoundError("文件夹不存在")
        return star_folder_repo.delete(folder_id)

    def assign_items(self, item_ids: list[str], folder_id: str | None) -> int:
        if folder_id is not None and not star_folder_repo.get(folder_id):
            raise NotFoundError("文件夹不存在")
        return star_folder_repo.assign(item_ids, folder_id)


# 全局单例
star_folder_service = StarFolderService()
