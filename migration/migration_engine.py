"""Main migration engine orchestrating the full migration process"""
import asyncio
from typing import Dict, Any, Optional
import json
from datetime import datetime, timezone
import logging

from clients.edge_client import EdgeClient
from clients.apigee_x_client import ApigeeXClient
from migration.edge_exporter import EdgeExporter
from migration.transformer import ResourceTransformer
from migration.x_importer import ApigeeXImporter
from migration.validator import MigrationValidator
from utils.logger import MigrationLogger
from models.migration_models import MigrationJob, MigrationStatus, ResourceStatus, MigrationResource

logger = logging.getLogger(__name__)


class MigrationEngine:
    """Orchestrate complete Edge to X migration"""
    
    def __init__(self, job: MigrationJob, mock_mode: bool = True):
        self.job = job
        self.mock_mode = mock_mode
        self.logger = MigrationLogger(job.id)
        
        # Initialize clients
        self.edge_client = EdgeClient(
            base_url="https://api.enterprise.apigee.com",
            org=job.edge_org,
            mock_mode=mock_mode
        )
        
        self.x_client = ApigeeXClient(
            project_id=f"project-{job.apigee_x_org}",
            organization=job.apigee_x_org,
            mock_mode=mock_mode
        )
        
        # Initialize migration components
        self.exporter = EdgeExporter(self.edge_client, self.logger)
        self.transformer = ResourceTransformer(self.logger)
        self.importer = ApigeeXImporter(self.x_client, self.logger, dry_run=job.dry_run)
        self.validator = MigrationValidator(self.edge_client, self.x_client, self.logger)
        
        # Storage for migration data
        self.edge_data: Optional[Dict[str, Any]] = None
        self.x_data: Optional[Dict[str, Any]] = None
        self.import_results: Optional[Dict[str, Any]] = None
    
    async def run_full_migration(self) -> MigrationJob:
        """Run complete migration pipeline"""
        try:
            self.job.status = MigrationStatus.EXPORTING
            self.job.started_at = datetime.now(timezone.utc)
            self.logger.info(f"Starting migration job: {self.job.name}")
            
            # Step 1: Export from Edge
            self.logger.info("=" * 60)
            self.logger.info("STEP 1: EXPORTING FROM APIGEE EDGE")
            self.logger.info("=" * 60)
            self.edge_data = await self.exporter.export_all(self.job.edge_env)
            self._update_resources_from_export(self.edge_data)
            
            # Step 2: Transform resources
            self.logger.info("=" * 60)
            self.logger.info("STEP 2: TRANSFORMING RESOURCES")
            self.logger.info("=" * 60)
            self.job.status = MigrationStatus.TRANSFORMING
            self.x_data = self.transformer.transform_all(self.edge_data)
            self._update_resources_from_transform(self.x_data)
            
            # Step 3: Import to Apigee X
            if not self.job.dry_run:
                self.logger.info("=" * 60)
                self.logger.info("STEP 3: IMPORTING TO APIGEE X")
                self.logger.info("=" * 60)
                self.job.status = MigrationStatus.IMPORTING
                self.import_results = await self.importer.import_all(self.x_data, self.job.apigee_x_env)
                self._update_resources_from_import(self.import_results)
            else:
                self.logger.info("DRY RUN: Skipping import step")
            
            # Step 4: Validation
            self.logger.info("=" * 60)
            self.logger.info("STEP 4: VALIDATING MIGRATION")
            self.logger.info("=" * 60)
            self.job.status = MigrationStatus.VALIDATING
            validation_report = await self.validator.validate_migration(
                self.edge_data, self.x_data, self.job.apigee_x_env, self.job.id
            )
            
            # Complete migration
            self.job.status = MigrationStatus.COMPLETED
            self.job.completed_at = datetime.now(timezone.utc)
            self.job.logs = self.logger.get_logs()
            self.job.errors = self.logger.get_errors()
            self.job.warnings = self.logger.get_warnings()
            
            self.logger.success("=" * 60)
            self.logger.success("MIGRATION COMPLETED SUCCESSFULLY")
            self.logger.success("=" * 60)
            self.logger.info(validation_report.summary)
            
        except Exception as e:
            self.job.status = MigrationStatus.FAILED
            self.job.completed_at = datetime.now(timezone.utc)
            self.job.errors = self.logger.get_errors()
            self.logger.error(f"Migration failed: {str(e)}")
            raise
        
        return self.job
    
    async def export_only(self) -> Dict[str, Any]:
        """Export resources from Edge only"""
        self.logger.info("Running export-only operation")
        self.edge_data = await self.exporter.export_all(self.job.edge_env)
        return self.edge_data
    
    async def transform_only(self, edge_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform Edge data to X format"""
        self.logger.info("Running transform-only operation")
        self.x_data = self.transformer.transform_all(edge_data)
        return self.x_data
    
    async def import_only(self, x_data: Dict[str, Any]) -> Dict[str, Any]:
        """Import transformed data to Apigee X"""
        self.logger.info("Running import-only operation")
        self.import_results = await self.importer.import_all(x_data, self.job.apigee_x_env)
        return self.import_results
    
    async def validate_only(self, edge_data: Dict[str, Any], x_data: Dict[str, Any]):
        """Validate migration"""
        self.logger.info("Running validation-only operation")
        return await self.validator.validate_migration(
            edge_data, x_data, self.job.apigee_x_env, self.job.id
        )
    
    def _update_resources_from_export(self, edge_data: Dict[str, Any]):
        """Update job resources from export data"""
        for resource_type, items in edge_data.items():
            if isinstance(items, list):
                for item in items:
                    name = item.get("name") or item.get("email", "unknown")
                    resource = MigrationResource(
                        resource_type=resource_type,
                        resource_name=name,
                        status=ResourceStatus.IN_PROGRESS,
                        edge_data=item
                    )
                    self.job.resources.append(resource)
        
        self.job.total_resources = len(self.job.resources)
    
    def _update_resources_from_transform(self, x_data: Dict[str, Any]):
        """Update resources with transformation data"""
        for resource in self.job.resources:
            # Find corresponding transformed data
            resource_list = x_data.get(resource.resource_type, [])
            for item in resource_list:
                name = item.get("name") or item.get("email")
                if name == resource.resource_name:
                    resource.x_data = item
                    break
    
    def _update_resources_from_import(self, import_results: Dict[str, Any]):
        """Update resources with import results"""
        imported = {(r["type"], r["name"]) for r in import_results.get("imported", [])}
        failed = {(r["type"], r["name"]): r.get("error") for r in import_results.get("failed", [])}
        
        for resource in self.job.resources:
            key = (resource.resource_type.rstrip('s'), resource.resource_name)  # Handle plural
            
            if key in imported:
                resource.status = ResourceStatus.SUCCESS
                self.job.completed_resources += 1
            elif key in failed:
                resource.status = ResourceStatus.FAILED
                resource.errors.append(failed[key])
                self.job.failed_resources += 1
            else:
                resource.status = ResourceStatus.SKIPPED
    
    def get_progress(self) -> Dict[str, Any]:
        """Get current migration progress"""
        return {
            "status": self.job.status,
            "total_resources": self.job.total_resources,
            "completed_resources": self.job.completed_resources,
            "failed_resources": self.job.failed_resources,
            "progress_percentage": (
                (self.job.completed_resources / self.job.total_resources * 100)
                if self.job.total_resources > 0 else 0
            ),
            "logs": self.logger.get_logs()[-10:],  # Last 10 logs
        }
