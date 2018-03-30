```
 __                              ___             __                            
/\ \__                          /\_ \           /\ \__  __                     
\ \ ,_\    __    ___ ___   _____\//\ \      __  \ \ ,_\/\_\    ___      __     
 \ \ \/  /'__`\/' __` __`\/\ '__`\\ \ \   /'__`\ \ \ \/\/\ \ /' _ `\  /'_ `\   
  \ \ \_/\  __//\ \/\ \/\ \ \ \L\ \\_\ \_/\ \L\.\_\ \ \_\ \ \/\ \/\ \/\ \L\ \  
   \ \__\ \____\ \_\ \_\ \_\ \ ,__//\____\ \__/.\_\\ \__\\ \_\ \_\ \_\ \____ \ 
    \/__/\/____/\/_/\/_/\/_/\ \ \/ \/____/\/__/\/_/ \/__/ \/_/\/_/\/_/\/___L\ \
                             \ \_\                                      /\____/
                              \/_/                                      \_/__/
```

# Templating

Templating is a Python module that combines an input *JSON data* with
a *text template* to produce another text file integrating the data. Templating
has the following features:

- Works with any text file
- Preserve white space and new-lines
- Supports conditional and loops
- Extensible value processing

Text templates contain **directives**, which are written like this:

```
${DIRECTIVE:ARG ARG…}
```

Here is a simple *hello world example*:

```
$ echo '${for:text}${this}${end}'      > hello.tmpl
$ echo '{"text":["Hello, ", "World"]}' > hello.json
$ templating hello.tmpl
Hello, World
```

Here are some design goals:

- Have a simple and efficient implementation
- Do not impose any structure on the source text file
- Work with JSON data

Non goals:

- Be a full-featured templating language (functions, computations, etc)
- Work with non-primitive data

## Directives

All the directives works with an *address* as the first argument. Addresses
indicate a path within the data, which is basically the sequences of keys
and indexes used to retrieve the data.

With the given data, the address `users.0.name` returns `"John"`.

```
{"users":[{name:"John"}]}
```

When using iterations, the current iterated value is bound to the special
`this` address.

```
${for:users}My name is ${this.name}${end}
```

### Substitution

The most common directive is substitution, which is takes the following
general form:

```
${ADDRESS|FORMAT}
```

### Translation

```
${T:LANG=TEXT…}
```

### With

```
${with:ADDRESS}
…
${end}
```

### Iterations

The general syntax for conditionals is as follows

```
${for:ADDRESS}
…
${empty}
…
${end}
```

Where the first block will be written as many times as there are 
elements in the value at the given `ADDRESS`. If there are no elements,
then the optional *empty block* will be written.


### Conditionals


The general syntax for conditionals is as follows

```
${if:ADDRESS OPERATOR VALUE}
…
${elif:ADDRESS OPERATOR VALUE}
…
${else}
…
${end}
```

where:

- `ADDRESS` is an **address** within the data
- `OPERATOR` (optional)  is one of `==`, `!=`, `>`, `<`, `<=` and `>=`. When
   prefixing the operator with `*` the operator will work on the number
   of items in the value resolved at the address.
- `VALUE` (optional) is either a *quoted string* or a *number*

The block `…` will only be written if the corresponding branch condition
is satisfied:

- When only `ADDRESS` is used, the corresponding should not be any of
  `null`, `0`, `{}` or `[]`

- When  `OPERATOR` and `VALUE` are used, the application of the
  `OPERATOR` to the resolved `ADDRESS` and `VALUE` must be true.


Here is a simple example:

```
The list is ${if:items}not empty${else}empty${end}.
```

Here is a more complex example

```
The list is has
${if:items*=0}
no elements
${elif:items*=1}
one element
${else}
many elements
${end}.
```



