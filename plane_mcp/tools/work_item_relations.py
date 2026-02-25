"""Work item relation-related tools for Plane MCP Server."""

from typing import Any, get_args

from fastmcp import FastMCP
from plane.models.enums import WorkItemRelationTypeEnum
from plane.models.work_items import (
    CreateWorkItemRelation,
    RemoveWorkItemRelation,
)

from plane_mcp.client import get_plane_client_context


def register_work_item_relation_tools(mcp: FastMCP) -> None:
    """Register all work item relation-related tools with the MCP server."""

    relation_buckets = (
        "blocking",
        "blocked_by",
        "duplicate",
        "relates_to",
        "start_after",
        "start_before",
        "finish_after",
        "finish_before",
    )

    def _is_not_found_error(err: Exception) -> bool:
        return "404" in str(err)

    def _extract_issue_id(value: Any) -> str | None:
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            nested_id = value.get("id")
            if isinstance(nested_id, str):
                return nested_id
        return None

    def _find_relation_id_by_related_issue(
        relations: dict[str, Any],
        target_related_issue_id: str,
    ) -> str | None:
        for bucket in relation_buckets:
            items = relations.get(bucket, [])
            if not isinstance(items, list):
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue

                relation_id = item.get("id")
                if not isinstance(relation_id, str):
                    continue

                related_issue = item.get("related_issue")
                related_issue_id = _extract_issue_id(related_issue)
                if related_issue_id == target_related_issue_id:
                    return relation_id

                issue = item.get("issue")
                issue_id = _extract_issue_id(issue)
                if issue_id == target_related_issue_id:
                    return relation_id

        return None

    @mcp.tool()
    def list_work_item_relations(
        project_id: str,
        work_item_id: str,
    ) -> dict[str, list[Any]]:
        """
        List relations for a work item.

        Args:
            project_id: UUID of the project
            work_item_id: UUID of the work item

        Returns:
            WorkItemRelationResponse containing lists of related work items by relation type:
            - blocking: Work items that are blocking this item
            - blocked_by: Work items that this item is blocked by
            - duplicate: Work items that are duplicates of this item
            - relates_to: Work items that relate to this item
            - start_after: Work items that start after this item
            - start_before: Work items that start before this item
            - finish_after: Work items that finish after this item
            - finish_before: Work items that finish before this item
        """
        client, workspace_slug = get_plane_client_context()
        response = client.work_items.relations.list(
            workspace_slug=workspace_slug,
            project_id=project_id,
            work_item_id=work_item_id,
        )

        # Plane deployments may return relation objects in each bucket (not only IDs).
        # Convert to plain dict so FastMCP does not enforce older SDK bucket item types.
        if hasattr(response, "model_dump"):
            return response.model_dump()  # type: ignore[return-value]
        return response

    @mcp.tool()
    def create_work_item_relation(
        project_id: str,
        work_item_id: str,
        relation_type: str,
        issues: list[str],
    ) -> None:
        """
        Create relations for a work item.

        Args:
            project_id: UUID of the project
            work_item_id: UUID of the work item
            relation_type: Type of relationship (blocking, blocked_by, duplicate,
                          relates_to, start_before, start_after, finish_before, finish_after)
            issues: List of work item IDs to create relations with
        """
        client, workspace_slug = get_plane_client_context()

        # Validate relation_type against allowed literal values
        if relation_type not in get_args(WorkItemRelationTypeEnum):
            raise ValueError(
                f"Invalid relation_type '{relation_type}'. "
                f"Must be one of: {get_args(WorkItemRelationTypeEnum)}"
            )
        validated_relation_type: WorkItemRelationTypeEnum = relation_type  # type: ignore[assignment]

        data = CreateWorkItemRelation(
            relation_type=validated_relation_type,
            issues=issues,
        )

        client.work_items.relations.create(
            workspace_slug=workspace_slug,
            project_id=project_id,
            work_item_id=work_item_id,
            data=data,
        )

    @mcp.tool()
    def remove_work_item_relation(
        project_id: str,
        work_item_id: str,
        related_issue: str,
    ) -> None:
        """
        Remove a relation from a work item.

        Args:
            project_id: UUID of the project
            work_item_id: UUID of the work item
            related_issue: UUID of the related work item to remove relation with
        """
        client, workspace_slug = get_plane_client_context()

        data = RemoveWorkItemRelation(related_issue=related_issue)

        try:
            client.work_items.relations.delete(
                workspace_slug=workspace_slug,
                project_id=project_id,
                work_item_id=work_item_id,
                data=data,
            )
            return
        except Exception as err:
            # Keep backward-compatible behavior first; only fallback on 404.
            if not _is_not_found_error(err):
                raise

            relations = list_work_item_relations(project_id, work_item_id)
            relation_id = _find_relation_id_by_related_issue(relations, related_issue)
            if relation_id is None:
                raise

            fallback_data = RemoveWorkItemRelation(related_issue=relation_id)
            client.work_items.relations.delete(
                workspace_slug=workspace_slug,
                project_id=project_id,
                work_item_id=work_item_id,
                data=fallback_data,
            )
