(class_declaration
  name: (identifier) @name.definition.class) @definition.class

(interface_declaration
  name: (identifier) @name.definition.interface) @definition.interface

(struct_declaration
  name: (identifier) @name.definition.class) @definition.class

(enum_declaration
  name: (identifier) @name.definition.class) @definition.class

(record_declaration
  name: (identifier) @name.definition.class) @definition.class

(method_declaration
  name: (identifier) @name.definition.method) @definition.method

(constructor_declaration
  name: (identifier) @name.definition.method) @definition.method

(invocation_expression
  function: (identifier) @name.reference.call) @reference.call

(invocation_expression
  function: (member_access_expression
    name: (identifier) @name.reference.call)) @reference.call

(object_creation_expression
  type: (identifier) @name.reference.class) @reference.class
