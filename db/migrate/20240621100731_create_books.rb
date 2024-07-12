class CreateBooks < ActiveRecord::Migration[7.1]
  def change
    create_table :books do |t|
      t.integer :publisher_id
      t.integer :author_id

      t.integer :page_count
      t.string :title
      t.text :description
      t.integer :published_year

      t.timestamps
      t.index :publisher_id
      t.index :author_id
    end
  end
end
