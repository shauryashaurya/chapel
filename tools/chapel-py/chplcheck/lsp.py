import chapel.core
from pygls.server import LanguageServer
from lsprotocol.types import TEXT_DOCUMENT_DID_OPEN, DidOpenTextDocumentParams
from lsprotocol.types import TEXT_DOCUMENT_DID_SAVE, DidSaveTextDocumentParams
from lsprotocol.types import Diagnostic, Range, Position, DiagnosticSeverity

def location_to_range(location):
    start = location.start()
    end = location.end()
    return Range(
        start=Position(start[0]-1, start[1]-1),
        end=Position(end[0]-1, end[1]-1)
    )

def run_lsp(driver):
    server = LanguageServer('chplcheck', 'v0.1')
    contexts = {}

    def get_updated_context(uri):
        if uri in contexts:
            context = contexts[uri]
            context.advance_to_next_revision(False)
        else:
            context = chapel.core.Context()
            contexts[uri] = context
        return context

    def parse_file(context, uri):
        return context.parse(uri[len("file://"):])

    def build_diagnostics(uri):
        context = get_updated_context(uri)
        asts = parse_file(context, uri)
        diagnostics = []
        for (node, rule) in driver.run_checks(context, asts):
            diagnostic = Diagnostic(
                range= location_to_range(node.location()),
                message="Lint: rule [{}] violated".format(rule),
                severity=DiagnosticSeverity.Warning
            )
            diagnostics.append(diagnostic)
        return diagnostics

    @server.feature(TEXT_DOCUMENT_DID_OPEN)
    async def did_open(ls, params: DidOpenTextDocumentParams):
        text_doc = ls.workspace.get_text_document(params.text_document.uri)
        ls.publish_diagnostics(text_doc.uri, build_diagnostics(text_doc.uri))

    @server.feature(TEXT_DOCUMENT_DID_SAVE)
    async def did_save(ls, params: DidSaveTextDocumentParams):
        text_doc = ls.workspace.get_text_document(params.text_document.uri)
        ls.publish_diagnostics(text_doc.uri, build_diagnostics(text_doc.uri))

    server.start_io()
