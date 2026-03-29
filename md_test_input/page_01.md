# Main Title: Hexagonal Architecture

Here is a paragraph about system design. We need to ensure that the inline HTML tags like <b>bold text</b> and <i>italic text</i> are not destroyed by the Markdown adapter.

## Subtitle: Code and Lists

When parsing Markdown, the AST (Abstract Syntax Tree) must preserve code blocks:

` ` `python
def example_function():
    # This is an English comment that should ideally be translated or preserved
    print("Hello, World!")
    return True
` ` `

Finally, we have a nested list to test boundary conditions:
1. First item with some **strong** emphasis.
2. Second item.
   * A sub-item that tests indentation.
   * Another sub-item.