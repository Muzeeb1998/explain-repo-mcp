(
  (method_definition
    name: (property_identifier) @name.definition.method) @definition.method
  (#not-eq? @name.definition.method "constructor")
)

(
  (pair
    key: (property_identifier) @name.definition.method
    value: [(function_expression) (arrow_function)]) @definition.method
)

(
  (variable_declarator
    name: (identifier) @name.definition.function
    value: [(function_expression) (arrow_function)]) @definition.function
)

(function_declaration
  name: (identifier) @name.definition.function) @definition.function

(generator_function_declaration
  name: (identifier) @name.definition.function) @definition.function

(class_declaration
  name: (identifier) @name.definition.class) @definition.class

(call_expression
  function: (identifier) @name.reference.call) @reference.call

(call_expression
  function: (member_expression
    property: (property_identifier) @name.reference.call)) @reference.call

(new_expression
  constructor: (identifier) @name.reference.class) @reference.class
