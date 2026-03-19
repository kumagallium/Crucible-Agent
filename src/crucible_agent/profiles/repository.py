"""プロファイル CRUD — DB 操作"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from crucible_agent.provenance.models import Profile
from crucible_agent.provenance.recorder import _session_factory

logger = logging.getLogger(__name__)


async def list_profiles() -> list[Profile]:
    """アクティブなプロファイル一覧を返す（名前順）"""
    async with _session_factory() as db:
        result = await db.execute(
            select(Profile).where(Profile.is_active == True).order_by(Profile.name)  # noqa: E712
        )
        return list(result.scalars().all())


async def get_profile(profile_id: str) -> Profile | None:
    """ID でプロファイルを取得する"""
    async with _session_factory() as db:
        result = await db.execute(
            select(Profile).where(Profile.id == profile_id, Profile.is_active == True)  # noqa: E712
        )
        return result.scalar_one_or_none()


async def get_profile_by_name(name: str) -> Profile | None:
    """名前でプロファイルを取得する"""
    async with _session_factory() as db:
        result = await db.execute(
            select(Profile).where(Profile.name == name, Profile.is_active == True)  # noqa: E712
        )
        return result.scalar_one_or_none()


async def create_profile(name: str, description: str, content: str) -> Profile:
    """プロファイルを作成する"""
    async with _session_factory() as db:
        profile = Profile(name=name, description=description, content=content)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
        logger.info("Profile created: %s (id=%s)", name, profile.id)
        return profile


async def update_profile(
    profile_id: str,
    name: str | None = None,
    description: str | None = None,
    content: str | None = None,
) -> Profile | None:
    """プロファイルを更新する。見つからない場合は None を返す"""
    async with _session_factory() as db:
        result = await db.execute(
            select(Profile).where(Profile.id == profile_id, Profile.is_active == True)  # noqa: E712
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            return None

        if name is not None:
            profile.name = name
        if description is not None:
            profile.description = description
        if content is not None:
            profile.content = content
        profile.updated_at = datetime.now(UTC)

        await db.commit()
        await db.refresh(profile)
        logger.info("Profile updated: %s (id=%s)", profile.name, profile.id)
        return profile


_DEFAULT_PROFILES = [
    {
        "name": "general",
        "description": "汎用AIアシスタント",
        "content": """\
あなたは汎用AIアシスタントです。

## 役割
ユーザーの質問に答え、利用可能なツールを活用してタスクを遂行します。

## 行動原則

1. ユーザーの意図を正確に理解してから行動する
2. 利用可能なツールがあれば積極的に活用する
3. 不確実な情報は断言せず、確信度を示す
4. 複雑なタスクはステップに分解して進める
5. エラーが発生した場合は原因と代替手段を提示する

## ツール使用ルール

- タスクに最適なツールを選択する
- 複数ツールの組み合わせが必要な場合、実行順序を明示する
- ツール実行が失敗した場合、エラー内容を伝え代替手段を提案する
- 3回以上同じエラーが続く場合は手動対応を提案する

## 出力形式

- 回答は簡潔かつ正確に
- 必要に応じてリスト・表・コードブロックを使用する
- 長い回答の場合は最初に要約を置く
""",
    },
    {
        "name": "science",
        "description": "実験科学研究支援アシスタント",
        "content": """\
あなたは実験科学の研究を支援するAIアシスタントです。

## 役割
研究者の実験計画の立案、データ解析、文献調査、実験記録の整理を支援します。
利用可能なツール（MCPサーバー）を活用して、正確で再現可能な研究成果に貢献します。

## 行動原則

1. 計画を立てるときは「目的 → 手法 → 期待結果 → 検証方法」の順で考える
2. 測定データを受け取ったら、まず外れ値と測定条件の妥当性を確認する
3. 生データを削除・上書きする操作は、必ず研究者の明示的な承認を得てから実行する
4. 不確実な情報は断言せず、確信度を示す（例: 「〜の可能性が高い」「〜と推定される」）
5. 文献引用は出典を明記する。出典が不明な場合はその旨を伝える

## ツール使用ルール

- 利用可能なツールを確認し、タスクに最適なツールを選択する
- 複数のツールを組み合わせるときは、データの受け渡しが正しいか確認する
- ツール実行が失敗した場合、エラー内容を研究者に伝え、代替手段を提案する
- 同じツールを3回以上失敗した場合は、手動対応を提案する

## 出力形式

- 実験計画は構造化ブロック（Human / Tool / AI ステップ）で出力する
- 解析結果は「結果 → 解釈 → 次のステップの提案」の順で述べる
- 数値データには単位を必ず付ける
- グラフや図が有効な場合はその生成を提案する

## 禁止事項

- 生データの無断削除・改変
- 根拠のない断定的結論
- 研究者の指示なしでの外部サービスへのデータ送信
- 安全性に関わる実験操作の省略提案
""",
    },
]


async def seed_default_profiles() -> None:
    """デフォルトプロファイルを投入する（既存の場合はスキップ）"""
    for p in _DEFAULT_PROFILES:
        existing = await get_profile_by_name(p["name"])
        if existing:
            logger.debug("Default profile '%s' already exists, skipping", p["name"])
            continue
        await create_profile(name=p["name"], description=p["description"], content=p["content"])
        logger.info("Default profile '%s' seeded", p["name"])


async def delete_profile(profile_id: str) -> bool:
    """プロファイルを論理削除する。成功した場合は True を返す"""
    async with _session_factory() as db:
        result = await db.execute(
            select(Profile).where(Profile.id == profile_id, Profile.is_active == True)  # noqa: E712
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            return False

        profile.is_active = False
        profile.updated_at = datetime.now(UTC)
        await db.commit()
        logger.info("Profile deleted: %s (id=%s)", profile.name, profile.id)
        return True
