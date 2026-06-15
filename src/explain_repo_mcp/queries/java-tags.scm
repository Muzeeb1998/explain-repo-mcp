(class_declaration
  name: (identifier) @name.definition.class) @definition.class

(enum_declaration
  name: (identifier) @name.definition.class) @definition.class

(interface_declaration
  name: (identifier) @name.definition.interface) @definition.interface

(method_declaration
  name: (identifier) @name.definition.method) @definition.method

(constructor_declaration
  name: (identifier) @name.definition.method) @definition.method

(method_invocation
  name: (identifier) @name.reference.call
  arguments: (argument_list) @reference.call)

(object_creation_expression
  type: (type_identifier) @name.reference.class) @reference.class

(superclass (type_identifier) @name.reference.class) @reference.class

(type_identifier) @name.reference.type @reference.type
