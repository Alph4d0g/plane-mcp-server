"""Work item relation-related tools for Plane MCP Server."""

from typing import Any, get_args

from fastmcp import FastMCP
from plane.models.enums import WorkItemRelationTypeEnum
from plane.models.work_items import CreateWorkItemRelation

from plane_mcp.client import get_plane_client_context


def register_work_item_relation_tools(mcp: FastMCP) -> None:
    """Register all work item relation-related tools with the MCP server."""

    def _is_route_not_found_error(err: Exception) -> bool:
        """Return True when an API error indicates a missing route."""
        text = str(err).lower()
        return "404" in text and "not found" in text

    def _work_item_relations_endpoint(
        workspace_slug: str, project_id: str, work_item_id: str
    ) -> str:
        return f"{workspace_slug}/projects/{project_id}/work-items/{work_item_id}/relations"

    def _work_item_remove_relation_endpoint(
        workspace_slug: str, project_id: str, work_item_id: str
    ) -> str:
        return f"{workspace_slug}/projects/{project_id}/work-items/{work_item_id}/remove-relation"

    def _legacy_issue_remove_relation_endpoint(
        workspace_slug: str, project_id: str, work_item_id: str
    ) -> str:
        return f"{workspace_slug}/projects/{project_id}/issues/{work_item_id}/remove-relation"

    def _fetch_relations_raw(project_id: str, work_item_id: str) -> dict[str, list[Any]]:
        """Fetch relation buckets as raw JSON to tolerate backend schema variants."""
        client, workspace_slug = get_plane_client_context()
        endpoint = _work_item_relations_endpoint(workspace_slug, project_id, work_item_id)

        response = client.work_items.relations._get(endpoint)  # type: ignore[attr-defined]
        if isinstance(response, dict):
            return response  # type: ignore[return-value]
        raise TypeError(f"Unexpected relations response type: {type(response).__name__}")

    def _remove_relation_raw(project_id: str, work_item_id: str, related_issue: str) -> None:
        """Remove a relation using current endpoint, with legacy fallback for compatibility."""
        client, workspace_slug = get_plane_client_context()
        payload = {"related_issue": related_issue}

        primary_endpoint = _work_item_remove_relation_endpoint(
            workspace_slug, project_id, work_item_id
        )
        try:
            client.work_items.relations._post(primary_endpoint, payload)  # type: ignore[attr-defined]
            return
        except Exception as err:
            if not _is_route_not_found_error(err):
                raise

        fallback_endpoint = _legacy_issue_remove_relation_endpoint(
            workspace_slug, project_id, work_item_id
        )
        client.work_items.relations._post(fallback_endpoint, payload)  # type: ignore[attr-defined]

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
        return _fetch_relations_raw(project_id, work_item_id)

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
        _remove_relation_raw(project_id, work_item_id, related_issue)
