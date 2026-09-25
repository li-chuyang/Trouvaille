"""Shared construction of Trouvaille's normal runtime stack."""

from dataclasses import dataclass

from trouvaille.agent import Agent
from trouvaille.context import ContextManager, ModelContextSummarizer
from trouvaille.execution import ExecutionBackend, LocalExecutionBackend
from trouvaille.lifecycle import LifecycleHooks
from trouvaille.model import Model
from trouvaille.project_instructions import ProjectInstructionsProvider, ProjectInstructionsStore
from trouvaille.repository import RepositoryContextProvider, RepositoryIndex
from trouvaille.tools import ToolRegistry, default_tools
from trouvaille.verification import EvidenceVerifier
from trouvaille.workspace import Workspace


@dataclass(frozen=True)
class RuntimeComponents:
    workspace: Workspace
    model: Model
    execution_backend: ExecutionBackend
    repository: RepositoryIndex
    project_instructions: ProjectInstructionsStore
    project_instructions_provider: ProjectInstructionsProvider
    repository_context_provider: RepositoryContextProvider
    context_manager: ContextManager
    verifier: EvidenceVerifier
    tools: ToolRegistry
    hooks: LifecycleHooks
    agent: Agent


def build_runtime(
    workspace: Workspace,
    model: Model,
    *,
    max_steps: int,
    execution_backend: ExecutionBackend | None = None,
) -> RuntimeComponents:
    """Build the same core Agent stack used by the CLI and evaluation harness."""

    backend = execution_backend if execution_backend is not None else LocalExecutionBackend()
    repository = RepositoryIndex(workspace, backend)
    project_instructions = ProjectInstructionsStore(workspace, repository)
    project_provider = ProjectInstructionsProvider(project_instructions)
    repository_provider = RepositoryContextProvider(repository)
    context_manager = ContextManager(ModelContextSummarizer(model))
    verifier = EvidenceVerifier()
    hooks = LifecycleHooks()
    hooks.add_before_model(project_provider.prepare)
    hooks.add_before_model(repository_provider.prepare)
    hooks.add_before_model(context_manager.prepare)
    hooks.add_before_finish(verifier.check)
    tools = default_tools(
        workspace,
        execution_backend=backend,
        repository=repository,
        project_instructions=project_instructions,
    )
    agent = Agent(model, tools, workspace, max_steps=max_steps, hooks=hooks)
    return RuntimeComponents(
        workspace=workspace,
        model=model,
        execution_backend=backend,
        repository=repository,
        project_instructions=project_instructions,
        project_instructions_provider=project_provider,
        repository_context_provider=repository_provider,
        context_manager=context_manager,
        verifier=verifier,
        tools=tools,
        hooks=hooks,
        agent=agent,
    )
