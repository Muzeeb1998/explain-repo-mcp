(struct_specifier
  name: (type_identifier) @name.definition.class
  body: (_)) @definition.class

(class_specifier
  name: (type_identifier) @name.definition.class
  body: (_)) @definition.class

(enum_specifier
  name: (type_identifier) @name.definition.class) @definition.class

(union_specifier
  name: (type_identifier) @name.definition.class) @definition.class

(function_definition
  declarator: (function_declarator
    declarator: (identifier) @name.definition.function)) @definition.function

(function_definition
  declarator: (function_declarator
    declarator: (field_identifier) @name.definition.method)) @definition.method

(function_definition
  declarator: (function_declarator
    declarator: (qualified_identifier
      name: (identifier) @name.definition.method))) @definition.method

(declaration
  declarator: (function_declarator
    declarator: (identifier) @name.definition.function)) @definition.function

(type_definition
  declarator: (type_identifier) @name.definition.type) @definition.type

(call_expression
  function: (identifier) @name.reference.call) @reference.call

(call_expression
  function: (field_expression
    field: (field_identifier) @name.reference.call)) @reference.call

(type_identifier) @name.reference.type @reference.type
