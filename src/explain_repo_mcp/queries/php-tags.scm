(class_declaration
  name: (name) @name.definition.class) @definition.class

(interface_declaration
  name: (name) @name.definition.interface) @definition.interface

(trait_declaration
  name: (name) @name.definition.class) @definition.class

(enum_declaration
  name: (name) @name.definition.class) @definition.class

(function_definition
  name: (name) @name.definition.function) @definition.function

(method_declaration
  name: (name) @name.definition.method) @definition.method

(function_call_expression
  function: (name) @name.reference.call) @reference.call

(member_call_expression
  name: (name) @name.reference.call) @reference.call

(object_creation_expression
  (name) @name.reference.class) @reference.class
