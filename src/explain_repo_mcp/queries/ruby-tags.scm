(class
  name: [(constant) (scope_resolution name: (constant) @name.definition.class)]) @definition.class

(module
  name: [(constant) (scope_resolution name: (constant) @name.definition.module)]) @definition.module

(method
  name: [(identifier) (constant)] @name.definition.method) @definition.method

(singleton_method
  name: [(identifier) (constant)] @name.definition.method) @definition.method

(call
  method: [(identifier) (constant)] @name.reference.call) @reference.call
